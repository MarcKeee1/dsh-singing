import unittest,tempfile,pathlib,sys,json,hashlib,time,os,urllib.request,urllib.error
from unittest.mock import patch,Mock
import numpy as np,soundfile as sf
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
import cache_catalog as c,bili_session as session

class CatalogTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name);(self.root/'performance-cache').mkdir()
 def record(self,index=1,**changes):
  key=hashlib.sha256(str(index).encode()).hexdigest();audio=self.root/'performance-cache'/(key+'.mp3');sf.write(audio,np.sin(np.arange(80000)*.08)*.1,8000,format='WAV')
  record={'ok':True,'seconds':10,'quality':{'passed':True,'voicedFrames':500},'voiceSignature':'current','audioSha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'sourceInfo':{'song':f'Song{index:02}','artist':'Singer','songId':str(index),'sourceProvider':'bilibili','sourcePage':'https://www.bilibili.com/video/BV1234567890','sourceComplete':True},**changes}
  audio.with_suffix('.json').write_text(json.dumps(record));return key,audio,record
 def test_public_list_and_exact_playback(self):
  key,audio,_=self.record();catalog=c.catalog(self.root,'current');self.assertEqual(catalog['total'],1);self.assertEqual(catalog['items'][0]['voice'],'当前音色')
  output=self.root/'out.mp3';result=c.materialize(self.root,key,output);self.assertTrue(result['cacheHit']);self.assertEqual(output.read_bytes(),audio.read_bytes())
 def test_private_and_corrupt_recordings_excluded(self):
  self.record(1,sourceInfo={'song':'private','artist':'owner','songId':'local:1','sourceProvider':'local'});self.record(2,quality={'passed':False});key,audio,_=self.record(3);audio.write_bytes(b'broken');self.assertEqual(c.catalog(self.root)['total'],0)
  with self.assertRaises(ValueError):c.materialize(self.root,key,self.root/'out.mp3')
 def test_pagination_old_voice_and_dedup(self):
  for n in range(15):self.record(n)
  self.record(30,sourceInfo={'song':'Song00','artist':'Singer','songId':'0','sourcePage':'https://music.163.com/song?id=1'})
  a=c.catalog(self.root,'different');b=c.catalog(self.root,'different',a['nextOffset']);self.assertEqual(a['total'],15);self.assertEqual(len(a['items']),12);self.assertEqual(b['items'][0]['number'],13);self.assertIsNone(b['nextOffset']);self.assertEqual(a['items'][0]['voice'],'以前保存的音色')
 def test_selection_revalidates_hash_and_id(self):
  key,audio,_=self.record();self.assertEqual(c.catalog(self.root)['total'],1);audio.write_bytes(audio.read_bytes()+b'modified')
  for value in (key,'../private','../'+key):
   with self.assertRaises(ValueError):c.materialize(self.root,value,self.root/'out.mp3')
 def test_small_delivery_limit_excludes_file(self):
  self.record();self.assertEqual(c.catalog(self.root,max_bytes=100)['total'],0)

class LoginTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
 def test_session_roundtrip_is_domain_scoped_and_encrypted_on_windows(self):
  session.save_session(self.root,[{'name':'SESSDATA','value':'TEST_ONLY_NOT_A_REAL_CREDENTIAL','expires':time.time()+60},{'name':'unrelated','value':'discard'}]);data=session.session_path(self.root).read_bytes()
  if os.name=='nt':self.assertNotIn(b'TEST_ONLY_NOT_A_REAL_CREDENTIAL',data)
  self.assertIn('SESSDATA=',session.cookie_header(self.root,'https://api.bilibili.com/x/test'))
  for url in ['https://evil.example','https://api.bilibili.com.evil.example','https://audio.bilivideo.com/test','http://api.bilibili.com/x','https://api.bilibili.com:444/x']:self.assertEqual(session.cookie_header(self.root,url),'')
 def test_expired_credentials_require_login(self):
  self.assertEqual(session.valid_cookies([{'name':'SESSDATA','value':'fixture','expires':1}]),[])
  with self.assertRaises(ValueError):session.save_session(self.root,[])
 def test_current_official_qr_host_and_key(self):
  from bili_login import validate_qr
  key='1'*32
  for base in ['https://account.bilibili.com/h5/account-h5/auth/scan-web','https://passport.bilibili.com/h5-app/passport/login/scan']:
   self.assertEqual(validate_qr({'url':base+'?qrcode_key='+key,'qrcode_key':key})['qrcode_key'],key)
  for url in ['https://account.bilibili.com.evil.example/h5/account-h5/auth/scan-web?qrcode_key='+key,'https://account.bilibili.com/h5/account-h5/auth/scan-web?qrcode_key=wrong']:
   with self.assertRaises(ValueError):validate_qr({'url':url,'qrcode_key':key})
 def test_redirect_cannot_leak_cookie(self):
  with self.assertRaises(ValueError):session.SameHostRedirect().redirect_request(urllib.request.Request('https://api.bilibili.com/x'),None,302,'redirect',{},'https://elsewhere.example')
 def test_authenticated_access_denial_has_no_automatic_retry_or_local_lock(self):
  session.save_session(self.root,[{'name':'SESSDATA','value':'test-only','expires':time.time()+60}])
  opener=Mock();opener.open.side_effect=urllib.error.HTTPError('https://api.bilibili.com',412,'denied',{},None)
  with patch('urllib.request.build_opener',return_value=opener):
   with self.assertRaises(urllib.error.HTTPError):session.open_request(self.root,urllib.request.Request('https://api.bilibili.com/x/test'))
  self.assertEqual(opener.open.call_count,1);self.assertFalse((self.root/'bilibili-access-cooldown.json').exists())

if __name__=='__main__':unittest.main()
