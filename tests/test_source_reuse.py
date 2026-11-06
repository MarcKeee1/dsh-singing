import pathlib,sys,tempfile,unittest,json,hashlib
import numpy as np,soundfile as sf
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
from source_reuse import find_verified_full
from singing_failure import from_job,public_details

class SourceReuse(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name);(self.root/'song-cache').mkdir();(self.root/'performance-cache').mkdir()
  self.source=self.root/'song-cache/original.wav';sf.write(self.source,np.zeros((16000*10,2)),16000)
  self.sha=hashlib.sha256(self.source.read_bytes()).hexdigest();self.audio=self.root/'performance-cache'/('a'*64+'.mp3');self.audio.write_bytes(b'verified converted audio')
  self.full={'sourceComplete':True,'sourceStartSeconds':0,'songId':'bili:example','song':'Test','artist':'Singer','sha256':self.sha,'seconds':10,'sourcePage':'https://www.bilibili.com/video/BV14V4y1H761','sourceProvider':'bilibili'}
  self.performance={'ok':True,'quality':{'passed':True},'audioSha256':hashlib.sha256(self.audio.read_bytes()).hexdigest(),'sourceInfo':{**self.full,'source':str(self.source),'sourceComplete':False,'sourceStartSeconds':3,'seconds':5}}
  self.save()
 def save(self):
  self.source.with_suffix('.json').write_text(json.dumps(self.full),'utf-8');self.audio.with_suffix('.json').write_text(json.dumps(self.performance),'utf-8')
 def test_full_original_from_successful_excerpt_skips_network(self):
  r=find_verified_full(self.root,'Test','Singer');self.assertEqual(r['seconds'],10);self.assertTrue(r['sourceComplete']);self.assertEqual(r['sourceStartSeconds'],0)
 def test_wrong_artist_title_or_explicit_version_never_reused(self):
  for song,artist,url in [('Other','Singer',''),('Test','Other',''),('Test','Singer','https://www.bilibili.com/video/BV1Ve41147Tu')]:self.assertIsNone(find_verified_full(self.root,song,artist,url))
 def test_corrupted_source_is_rejected(self):
  self.source.write_bytes(b'corrupt');self.assertIsNone(find_verified_full(self.root,'Test','Singer'))
 def test_corrupted_performance_does_not_prove_the_original(self):
  self.audio.write_bytes(b'corrupt');self.assertIsNone(find_verified_full(self.root,'Test','Singer'))
 def test_local_or_short_source_cannot_masquerade_as_full(self):
  self.full['sourceComplete']=False;self.save();self.assertIsNone(find_verified_full(self.root,'Test','Singer'))
  self.full['sourceComplete']=True;self.performance['sourceInfo']['sourceProvider']='local';self.save();self.assertIsNone(find_verified_full(self.root,'Test','Singer'))
 def test_unknown_stage_is_explicitly_unknown(self):
  error=from_job(self.root);self.assertEqual(public_details(error)['failureCode'],'local_processing_failed');self.assertNotIn(str(self.root),str(error))
 def test_no_vocals_is_not_reported_as_length_or_separation_crash(self):
  (self.root/'stages.json').write_text(json.dumps({'failedStage':'vocalValidation','errorMessage':'This excerpt contains too little singing'}))
  d=public_details(from_job(self.root));self.assertEqual(d['failureStage'],'vocal_validation');self.assertEqual(d['failureCode'],'no_usable_vocals')
 def test_harmony_error_and_timeout_keep_their_stage(self):
  (self.root/'stages.json').write_text(json.dumps({'failedStage':'harmonyQuality'}));self.assertEqual(public_details(from_job(self.root))['failureCode'],'harmony_pitch_failed')
  self.assertEqual(public_details(from_job(self.root,timeout=True))['failureCode'],'processing_timeout')

if __name__=='__main__':unittest.main()
