"""User-operated NetEase login, kept locally and scoped to its official API."""
import http.cookiejar
import base64
import json
import os
import pathlib
import secrets
import string
import time
import urllib.parse
import urllib.request
import uuid

from bili_session import protect

BASE = 'https://music.163.com'
COOKIE_NAMES = {'MUSIC_U', '__csrf', 'NMTID'}
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': BASE + '/'}
WEB_KEY = b'0CoJUm6Qyw8W8jud'
WEB_IV = b'0102030405060708'
WEB_PUBLIC_KEY = '''-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDgtQn2JZ34ZC28NWYpAUd98iZ37BUrX/aKzmFbt7clFSs6sXqHauqKWqdtLkF2KexO40H1YTX8z2lSgBBOAxLsvaklV8k4cBFK9snQXE9/DDaFt6Rr7iVZMldczhC0JNgTz+SHXT6CBHuX3e9SdB1Ua44oncaTWz7OBGLbCiK45wIDAQAB
-----END PUBLIC KEY-----'''


def web_request(url, form, rows=()):
    """Encode the ordinary web-player form; no third-party login proxy."""
    from Crypto.Cipher import AES
    from Crypto.PublicKey import RSA
    from Crypto.Util.Padding import pad
    if not api_url(url):
        raise ValueError('网易云接口地址无效')
    parsed = urllib.parse.urlparse(url)
    fields = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    fields.update(form)
    fields['csrf_token'] = next((r['value'] for r in rows if r['name'] == '__csrf'), '')
    secret = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16)).encode()
    def encrypt(data, key):
        return base64.b64encode(AES.new(key, AES.MODE_CBC, WEB_IV).encrypt(pad(data, 16)))
    first = encrypt(json.dumps(fields, ensure_ascii=False, separators=(',', ':')).encode(), WEB_KEY)
    params = encrypt(first, secret).decode()
    public = RSA.import_key(WEB_PUBLIC_KEY)
    enc = format(pow(int.from_bytes(secret[::-1], 'big'), public.e, public.n), '0256x')
    target = urllib.parse.urlunparse(parsed._replace(path='/weapi/' + parsed.path[5:], query=''))
    headers = dict(HEADERS)
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    request = urllib.request.Request(target, data=urllib.parse.urlencode({'params': params, 'encSecKey': enc}).encode(), headers=headers)
    if rows:
        request.add_unredirected_header('Cookie', '; '.join(r['name'] + '=' + r['value'] for r in rows))
    return request


def session_path(root):
    return pathlib.Path(root) / '.auth' / ('netease.dpapi' if os.name == 'nt' else 'netease.session')


def valid_cookies(rows):
    if not isinstance(rows, list):
        raise ValueError('登录 Cookie 格式无效')
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name, value, expires = row.get('name'), row.get('value'), row.get('expires')
        if (name not in COOKIE_NAMES or not isinstance(value, str) or not value
                or len(value) > 4096 or any(ord(c) < 33 or ord(c) > 126 or c in ';,' for c in value)):
            continue
        if expires is not None:
            try:
                expires = float(expires)
                if not time.time() < expires < 1e12:
                    continue
            except (TypeError, ValueError):
                continue
        result[name] = {'name': name, 'value': value, 'expires': expires}
    return list(result.values())


def save_session(root, rows):
    rows = valid_cookies(rows)
    if not any(r['name'] == 'MUSIC_U' for r in rows):
        raise ValueError('网易云没有返回有效登录状态，请重新扫码并在手机确认')
    path = session_path(root)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    payload = protect(json.dumps({'cookies': rows}).encode())
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_session(root):
    path = session_path(root)
    if not path.is_file():
        return []
    try:
        if path.stat().st_size > 65536:
            raise ValueError()
        rows = valid_cookies(json.loads(protect(path.read_bytes(), True))['cookies'])
        if not any(r['name'] == 'MUSIC_U' for r in rows):
            raise ValueError()
        return rows
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError('网易云本机登录状态已失效，请重新扫码或退出插件登录') from None


def api_url(url):
    try:
        parsed = urllib.parse.urlparse(url)
        return (parsed.scheme == 'https' and parsed.hostname == 'music.163.com'
                and not parsed.username and not parsed.password and parsed.port in (None, 443)
                and parsed.path.startswith(('/api/', '/weapi/')))
    except ValueError:
        return False


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not api_url(newurl):
            raise ValueError('网易云接口发生异常跳转，已停止')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_request(root, request):
    if not api_url(request.full_url):
        raise ValueError('网易云登录状态只允许用于官方 HTTPS API')
    rows = load_session(root)
    form = dict(urllib.parse.parse_qsl((request.data or b'').decode('utf-8'), keep_blank_values=True))
    if not urllib.parse.urlparse(request.full_url).path.startswith('/api/'):
        raise ValueError('网易云请求应使用原始 API 地址')
    request = web_request(request.full_url, form, rows)
    return urllib.request.build_opener(SameHostRedirect()).open(request, timeout=20)


def read_json(response):
    raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('网易云接口返回内容过大')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('网易云接口返回格式无效')
    return data


def login_status(root):
    request = urllib.request.Request(BASE + '/api/w/nuser/account/get', data=b'', headers=HEADERS)
    with open_request(root, request) as response:
        data = read_json(response)
    if data.get('code') != 200:
        raise ValueError('网易云暂时无法检查登录状态，请稍后再试')
    return bool((data.get('account') or {}).get('id'))


class Login:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(SameHostRedirect(), urllib.request.HTTPCookieProcessor(self.jar))

    def api(self, path, form):
        url = BASE + '/api/' + path
        if not api_url(url):
            raise ValueError('登录接口地址无效')
        request = web_request(url, form, [{'name': c.name, 'value': c.value} for c in self.jar if c.name in COOKIE_NAMES])
        try:
            with self.opener.open(request, timeout=15) as response:
                return read_json(response)
        except Exception:
            raise ValueError('网易云登录暂不可用，请在官方客户端处理验证后再试') from None

    def generate(self):
        import re
        data = self.api('login/qrcode/unikey', {'type': 3})
        key = data.get('unikey', '')
        if data.get('code') != 200 or not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key):
            raise ValueError('网易云没有返回有效二维码，请稍后重新申请')
        return {'key': key, 'url': BASE + '/login?' + urllib.parse.urlencode({'codekey': key})}

    def poll(self, key):
        data = self.api('login/qrcode/client/login', {'key': key, 'type': 3})
        try:
            code = int(data.get('code', 0))
        except (ValueError, TypeError):
            code = 0
        if code == 8821:
            raise ValueError('网易云要求网页验证（8821），请点击下方“官方网页登录”完成登录')
        if code not in (800, 801, 802, 803):
            raise ValueError('网易云登录返回状态码 ' + str(code) + '，请在官方客户端处理验证后重试')
        return code

    def save(self, root):
        rows = [{'name': c.name, 'value': c.value, 'expires': c.expires} for c in self.jar
                if c.name in COOKIE_NAMES and c.domain.lstrip('.') in {'music.163.com', '163.com'}]
        save_session(root, rows)
