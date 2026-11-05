"""Optional user-authorized session. No browser scraping or access-denial retries."""
import ctypes,json,os,pathlib,time,urllib.request,urllib.error,urllib.parse

COOKIE_NAMES={'SESSDATA','bili_jct','DedeUserID','DedeUserID__ckMd5'}
AUTH_HOSTS={'api.bilibili.com','www.bilibili.com','passport.bilibili.com'}

def protect(data,decrypt=False):
    if os.name!='nt':return data
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)];fn.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('本机登录信息无法解密，请重新登录' if decrypt else '无法安全保存登录状态')
    try:return ctypes.string_at(target.pbData,target.cbData)
    finally:kernel.LocalFree(target.pbData)

def session_path(root):return pathlib.Path(root)/'.auth'/('bilibili.dpapi' if os.name=='nt' else 'bilibili.session')

def valid_cookies(rows):
    result=[]
    for row in rows:
        name=row.get('name');value=str(row.get('value',''));expires=row.get('expires')
        if name not in COOKIE_NAMES or not value or len(value)>4096 or any(ord(c)<32 or c in ';\r\n' for c in value):continue
        if expires is not None and float(expires)<=time.time():continue
        result.append({'name':name,'value':value,'expires':expires})
    return result

def save_session(root,rows):
    rows=valid_cookies(rows)
    if not any(r['name']=='SESSDATA' for r in rows):raise ValueError('登录没有返回有效会话，请在官方页面完成验证后再试')
    path=session_path(root);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    payload=protect(json.dumps({'cookies':rows}).encode());temporary=path.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'wb') as f:f.write(payload)
    temporary.replace(path)

def cookie_header(root,url):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in AUTH_HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):return ''
    path=session_path(root)
    if not path.is_file():return ''
    try:
        if path.stat().st_size>65536:raise ValueError()
        rows=valid_cookies(json.loads(protect(path.read_bytes(),True))['cookies'])
    except (OSError,ValueError,TypeError,KeyError):raise ValueError('B站本地登录状态已不可用，请重新登录或退出后匿名使用') from None
    if not any(r['name']=='SESSDATA' for r in rows):raise ValueError('B站登录已过期，请重新登录或退出后匿名使用')
    return '; '.join(r['name']+'='+r['value'] for r in rows)

class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        old,new=urllib.parse.urlparse(req.full_url),urllib.parse.urlparse(newurl)
        if new.scheme!='https' or new.hostname!=old.hostname or new.username or new.password or new.port not in (None,443):raise ValueError('B站登录请求发生异常跳转，已停止')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def open_request(root,request):
    cookie=cookie_header(root,request.full_url)
    if cookie:request.add_unredirected_header('Cookie',cookie)
    return urllib.request.build_opener(SameHostRedirect()).open(request,timeout=20)

def is_blocked(error):
    seen=set()
    while error and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error,urllib.error.HTTPError) and error.code in {401,403,412,429}:return True
        if any(t in str(error) for t in ['限制了这次访问','限制了短链接访问']):return True
        error=error.__cause__
    return False

