import unittest,tempfile,pathlib,sys,json,hashlib
import numpy as np,soundfile as sf
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
from cache_catalog import catalog,materialize
from performance_library import find_performance
class CatalogPolicy(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name);(self.root/'performance-cache').mkdir()
 def add(self,n,seconds,song='Song',artist='Singer',complete=False):
  id=hashlib.sha256(str(n).encode()).hexdigest();audio=self.root/'performance-cache'/(id+'.mp3');sf.write(audio,np.sin(np.arange(seconds*8000)*.08)*.1,8000,format='WAV')
  r={'ok':True,'seconds':seconds,'voiceSignature':'current','quality':{'passed':True,'voicedFrames':seconds*80},'audioSha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'requestSpec':{'title':song,'artist':artist,'duration':seconds,'mode':'excerpt'},'sourceInfo':{'song':song,'artist':artist,'songId':str(n),'sourcePage':'https://www.bilibili.com/video/BV1234567890','sourceProvider':'bilibili','sourceComplete':complete}}
  audio.with_suffix('.json').write_text(json.dumps(r),'utf-8');return id,audio
 def test_short_only_song_stays_visible_and_shorter_duplicate_is_still_reusable(self):
  id,audio=self.add(1,12);before=audio.read_bytes();result=catalog(self.root,'current');self.assertEqual(result['total'],1)
  longer,_=self.add(2,60);result=catalog(self.root,'current');self.assertEqual(result['total'],1);self.assertEqual(result['items'][0]['cacheId'],longer)
  hit=find_performance(self.root,{'title':'Song','artist':'Singer','duration':12,'mode':'excerpt'},'current');self.assertIsNotNone(hit);self.assertEqual(hit[0],audio)
  output=self.root/'selected.mp3';self.assertTrue(materialize(self.root,id,output,'current')['cacheHit']);self.assertEqual(output.read_bytes(),before);self.assertEqual(audio.read_bytes(),before)
 def test_one_longest_version_per_song_artist_and_longest_first(self):
  self.add(1,45);longest,_=self.add(2,90);other,_=self.add(3,60,'Other');self.add(4,40,'Song','Another Singer')
  result=catalog(self.root,'current');self.assertEqual(result['total'],3);self.assertEqual([x['seconds'] for x in result['items']],[90,60,40]);self.assertEqual(result['items'][0]['cacheId'],longest);self.assertEqual(result['hiddenCount'],1)
 def test_actual_longest_wins_over_section_labels_and_no_minimum_duration(self):
  longest,_=self.add(1,90);self.add(2,80,complete=True);tiny,_=self.add(3,10,'Short Whole',complete=True)
  result=catalog(self.root,'current');self.assertEqual([x['cacheId'] for x in result['items']],[longest,tiny])
 def test_title_normalization_deduplicates_but_artist_identity_stays(self):
  self.add(1,45,'Song','A &amp; B');longest,_=self.add(2,60,'Ｓｏｎｇ','A & B');self.add(3,50,'Song','C')
  result=catalog(self.root,'current');self.assertEqual(result['total'],2);self.assertEqual(result['items'][0]['cacheId'],longest)
 def test_pagination_tracks_visible_items_only(self):
  for n in range(14):self.add(n,45+n,'Song'+str(n))
  self.add(90,8,'Preview');a=catalog(self.root,'current');b=catalog(self.root,'current',a['nextOffset']);self.assertEqual(a['total'],15);self.assertEqual(len(a['items']),12);self.assertEqual(b['items'][0]['number'],13);self.assertIsNone(b['nextOffset']);self.assertEqual(b['items'][-1]['seconds'],8)
if __name__=='__main__':unittest.main()
