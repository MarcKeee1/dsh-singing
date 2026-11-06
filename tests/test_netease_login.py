import io
import json
import os
import pathlib
import sys
import tempfile
import threading
import subprocess
import time
import unittest
import urllib.parse
import urllib.request
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'python'))
import netease_session as session
from netease_login import wait_login


class NetEaseLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.rows = [{'name': 'MUSIC_U', 'value': 'test-local-session', 'expires': time.time() + 3600},
                     {'name': '__csrf', 'value': 'test-csrf', 'expires': None}]

    def test_session_roundtrip_encrypts_on_windows_and_ignores_other_cookies(self):
        session.save_session(self.root, self.rows + [{'name': 'irrelevant', 'value': 'unused'}])
        self.assertEqual(session.load_session(self.root), self.rows)
        path = session.session_path(self.root)
        if os.name == 'nt':
            self.assertNotIn(b'test-local-session', path.read_bytes())
        else:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(path.parent.glob('*.tmp')), [])

    def test_expired_or_malformed_credentials_never_become_headers(self):
        for value in ['', 'bad; injected=yes', 'bad\r\nX:yes', 'bad value']:
            with self.assertRaises(ValueError):
                session.save_session(self.root, [{'name': 'MUSIC_U', 'value': value}])
        with self.assertRaises(ValueError):
            session.save_session(self.root, [{'name': 'MUSIC_U', 'value': 'old', 'expires': 1}])
        with self.assertRaises(ValueError):
            session.save_session(self.root, [{'name': 'MUSIC_U', 'value': 'old', 'expires': float('nan')}])
        session.session_path(self.root).parent.mkdir(exist_ok=True)
        session.session_path(self.root).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, '重新扫码'):
            session.load_session(self.root)

    def test_cookie_and_csrf_reach_only_the_official_api(self):
        session.save_session(self.root, self.rows)
        opener = Mock()
        with patch.object(session.urllib.request, 'build_opener', return_value=opener):
            request = urllib.request.Request(session.BASE + '/api/song/enhance/player/url', data=b'ids=%5B1%5D&csrf_token=wrong')
            with patch.object(session.secrets,'choice',return_value='a'):
                session.open_request(self.root, request)
            actual = opener.open.call_args.args[0]
            self.assertIn('MUSIC_U=test-local-session', actual.get_header('Cookie'))
            self.assertEqual(actual.full_url,session.BASE+'/weapi/song/enhance/player/url')
            encoded=urllib.parse.parse_qs(actual.data.decode())
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad
            import base64
            first=unpad(AES.new(b'a'*16,AES.MODE_CBC,session.WEB_IV).decrypt(base64.b64decode(encoded['params'][0])),16)
            plain=unpad(AES.new(session.WEB_KEY,AES.MODE_CBC,session.WEB_IV).decrypt(base64.b64decode(first)),16)
            fields=json.loads(plain)
            self.assertEqual(fields['csrf_token'],'test-csrf')
            self.assertEqual(fields['ids'],'[1]')
            self.assertEqual(len(encoded['encSecKey'][0]),256)
            self.assertEqual(opener.open.call_count, 1)
            for url in ['https://music.163.com.evil.invalid/api/test', 'http://music.163.com/api/test',
                        'https://music.163.com:444/api/test', 'https://user@music.163.com/api/test',
                        'https://m10.music.126.net/audio.mp3', 'https://music.163.com/login']:
                with self.assertRaises(ValueError):
                    session.open_request(self.root, urllib.request.Request(url))
            self.assertEqual(opener.open.call_count, 1)

    def test_redirect_does_not_export_auth_to_another_origin(self):
        handler = session.SameHostRedirect()
        request = urllib.request.Request(session.BASE + '/api/test')
        for url in ['https://other.invalid/api/test', 'http://music.163.com/api/test', 'https://music.163.com/login']:
            with self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, 'Found', {}, url)

    def test_qr_is_constructed_on_the_official_domain_and_bad_key_stops(self):
        login = session.Login()
        with patch.object(login, 'api', return_value={'code': 200, 'unikey': 'a' * 36}):
            self.assertEqual(login.generate()['url'], session.BASE + '/login?codekey=' + 'a' * 36)
        for data in [{'code': 200, 'unikey': 'https://other.invalid'}, {'code': 403}, {'code': 200, 'unikey': {}}]:
            with patch.object(login, 'api', return_value=data), self.assertRaises(ValueError):
                login.generate()

    def test_qr_states_save_only_after_phone_confirmation(self):
        login = Mock()
        login.generate.return_value = {'key': 'key', 'url': session.BASE + '/login?codekey=key'}
        login.poll.side_effect = [801, 802, 803]
        cancel = Mock()
        cancel.wait.return_value = False
        cancel.is_set.return_value = False
        events = []
        wait_login(login, self.root, cancel, lambda *event: events.append(event))
        self.assertEqual(login.poll.call_count, 3)
        login.save.assert_called_once_with(self.root)
        self.assertTrue(any('手机' in text or 'App' in text for kind, text in events if kind == 'status'))
        self.assertEqual(events[-1][0], 'done')

    def test_expiry_cancellation_and_verification_do_not_save(self):
        for code in [800, 803]:
            login = Mock()
            login.generate.return_value = {'key': 'key', 'url': 'url'}
            login.poll.return_value = code
            cancel = Mock()
            cancel.wait.return_value = False
            cancel.is_set.return_value = code == 803
            wait_login(login, self.root, cancel, lambda *_: None)
            login.save.assert_not_called()
        login = session.Login()
        with patch.object(login, 'api', return_value={'code': 8821}), self.assertRaises(ValueError):
            login.poll('key')
        with patch.object(login, 'api', side_effect=ValueError('verification')), self.assertRaises(ValueError):
            wait_login(login, self.root, threading.Event(), lambda *_: None)

    def test_status_requires_an_account_and_response_is_bounded(self):
        for account, expected in [(None, False), ({'id': 123}, True)]:
            with patch.object(session, 'open_request', return_value=io.BytesIO(json.dumps({'code': 200, 'account': account}).encode())):
                self.assertEqual(session.login_status(self.root), expected)
        with self.assertRaises(ValueError):
            session.read_json(io.BytesIO(b' ' * (2 * 1024 * 1024 + 1)))

    def test_official_window_imports_session_via_stdin_without_exposing_it(self):
        script=pathlib.Path(__file__).resolve().parents[1]/'python/netease_login.py'
        command=[sys.executable,str(script),'--data-dir',str(self.root),'--import-session']
        done=subprocess.run(command,input=json.dumps(self.rows).encode(),capture_output=True,timeout=10)
        self.assertEqual(done.returncode,0)
        self.assertEqual(done.stdout,b'')
        self.assertEqual(done.stderr,b'')
        self.assertEqual(session.load_session(self.root),self.rows)
        done=subprocess.run(command,input=b'['+b' '*65536+b']',capture_output=True,timeout=10)
        self.assertNotEqual(done.returncode,0)
        self.assertEqual(session.load_session(self.root),self.rows)

    def test_verification_is_actionable_and_is_never_polled_repeatedly(self):
        login=session.Login()
        with patch.object(login,'api',return_value={'code':8821}) as call,self.assertRaisesRegex(ValueError,'官方网页登录'):
            login.poll('key')
        self.assertEqual(call.call_count,1)


if __name__ == '__main__':
    unittest.main()
