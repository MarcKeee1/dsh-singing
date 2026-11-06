import unittest,tempfile,pathlib,json,hashlib,sys,numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
from song_position import request_position,PositionError
from performance_library import find_performance
from harmony_vocal import mix

class PositionAndCache(unittest.TestCase):
 def test_null_occurrence_is_omitted_but_bad_values_still_rejected(self):
  self.assertIsNone(request_position({'start':0,'lyric_occurrence':None}))
  self.assertEqual(request_position({'start':0,'positionVersion':1,'lyric_occurrence':None})['startSeconds'],0)
  for bad in (0,False,11,'1',1.5):
   with self.assertRaises(PositionError):request_position({'lyric_occurrence':bad})
 def test_duplicate_alias_same_verified_audio_can_be_reused_but_different_versions_cannot(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);cache=root/'performance-cache';cache.mkdir()
   def write(id,songid,payload):
    m={'ok':True,'song':'Test','seconds':56,'voiceSignature':'voice','quality':{'passed':True,'voicedFrames':2000},
       'sourceInfo':{'song':'Test','artist':'Singer','songId':songid,'chorusMethod':'complete_section'},
       'requestSpec':{'mode':'chorus','lyric_occurrence':None},'audioSha256':hashlib.sha256(payload).hexdigest()}
    (cache/(id+'.mp3')).write_bytes(payload);(cache/(id+'.json')).write_text(json.dumps(m),encoding='utf-8')
   write('a'*64,'old-id',b'verified-audio');write('b'*64,'new-id',b'verified-audio')
   q={'title':'Test','artist':'Singer','mode':'chorus'}
   self.assertIsNotNone(find_performance(root,q,'voice'))
   write('b'*64,'new-id',b'different-performance')
   self.assertIsNone(find_performance(root,q,'voice'))
   self.assertIsNone(find_performance(root,{**q,'artist':'Other'},'voice'))
class HarmonyMix(unittest.TestCase):
 def test_harmony_finishes_after_main_without_moving_time_or_adding_raw_voice(self):
  sr=1000;n=4000;t=np.arange(n)/sr
  lead=(.1*np.sin(2*np.pi*200*t))[:,None];lead[2000:]=0
  harmonic=(.08*np.sin(2*np.pi*150*t))[:,None];harmonic[:1500]=0;harmonic[3500:]=0
  music=np.zeros((n,2));mixed,info=mix(lead,music,lead,sr,harmonic,harmonic)
  self.assertEqual(mixed.shape,music.shape)
  self.assertGreater(float(np.sqrt(np.mean(mixed[2200:3300]**2))),.01)
  self.assertLess(float(np.max(np.abs(mixed[3500:]))),1e-9)
  self.assertEqual(info['harmonyVersion'],1)
  silent,_=mix(lead,music,lead,sr,harmonic,np.zeros_like(harmonic))
  self.assertLess(float(np.max(np.abs(silent[2200:3300]))),1e-9)
 def test_misaligned_tracks_are_rejected(self):
  audio=np.ones((1000,1))*.1
  with self.assertRaises(ValueError):mix(audio,audio,audio,1000,audio,audio[:500])
if __name__=='__main__':unittest.main()
