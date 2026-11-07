import unittest,os,json,pathlib,tempfile,sys
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
import runtime
class PluginSettings(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=pathlib.Path(self.temp.name)/'backend.json';self.path.write_text(json.dumps({'ffmpeg':sys.executable,'voiceGain':1.2}),'utf-8')
 def test_ui_overrides_and_backend_preservation(self):
  before=self.path.read_bytes()
  with patch.dict(os.environ,{'DSH_SINGING_UI_SETTINGS':json.dumps({'autoOctave':False,'autoSoloGuard':False,'musicGain':.4})}):config=runtime.load_config(self.path)
  self.assertFalse(config['autoOctave']);self.assertFalse(config['autoSoloGuard']);self.assertEqual(config['musicGain'],.4);self.assertEqual(config['voiceGain'],1.2);self.assertEqual(self.path.read_bytes(),before)
 def test_unknown_or_invalid_values_are_rejected(self):
  for value in [{'dataDir':'escape'},{'autoOctave':'false'},{'autoSoloGuard':'false'},{'musicGain':0},{'voiceGain':True},{'voiceGain':float('nan')},[]]:
   with self.subTest(value=value),patch.dict(os.environ,{'DSH_SINGING_UI_SETTINGS':json.dumps(value)}),self.assertRaises(ValueError):runtime.load_config(self.path)
 def test_settings_invalidate_performance_signature(self):
  import voice_reference
  reference=pathlib.Path(self.temp.name)/'reference.wav';reference.write_bytes(b'test fixture only')
  with patch.dict(voice_reference.CONFIG,{'referenceAudio':reference,'autoOctave':True,'voiceGain':1.25,'musicGain':.55,'harmonyGain':.8,'shortenGaps':True}):
   first=voice_reference.voice_signature()[0]
   voice_reference.CONFIG['autoSoloGuard']=False;self.assertNotEqual(first,voice_reference.voice_signature()[0]);voice_reference.CONFIG['autoSoloGuard']=True
   voice_reference.CONFIG['autoOctave']=False;self.assertNotEqual(first,voice_reference.voice_signature()[0])
if __name__=='__main__':unittest.main()
