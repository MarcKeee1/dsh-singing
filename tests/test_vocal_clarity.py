import pathlib,sys,unittest,numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
from singing_mix import clarify_vocal,mix_tracks
class VocalClarity(unittest.TestCase):
 def test_frequency_and_length_stay_while_low_mid_is_reduced_and_presence_lifted(self):
  sr=16000;t=np.arange(sr*2)/sr
  for hz in [140,280,2900]:
   wave=.1*np.sin(2*np.pi*hz*t);original=wave.copy();clear=clarify_vocal(wave,sr);np.testing.assert_array_equal(wave,original)
   self.assertEqual(len(clear),len(wave));body=clear[sr//2:sr+sr//2];self.assertEqual(np.argmax(np.abs(np.fft.rfft(body))),hz)
   gain=20*np.log10(np.std(body)/np.std(wave[sr//2:sr+sr//2]))
   if hz==280:self.assertLess(gain,-1.2)
   if hz==2900:self.assertGreater(gain,1.4)
 def test_high_harmony_gets_no_extra_presence_boost(self):
  sr=16000;t=np.arange(sr*2)/sr;wave=np.sin(2*np.pi*5000*t);clear=clarify_vocal(wave,sr,harmony=True)
  self.assertLess(20*np.log10(np.std(clear[1000:-1000])/np.std(wave[1000:-1000])),.05)
 def test_mix_still_respects_peak_and_channel_alignment(self):
  sr=16000;t=np.arange(sr)/sr;voice=.1*np.sin(2*np.pi*220*t)[:,None];mixed,settings=mix_tracks(voice,np.zeros((sr,2)),voice,sr)
  self.assertEqual(mixed.shape,(sr,2));self.assertLessEqual(float(np.max(np.abs(mixed))),.89001);self.assertEqual(settings['clarity']['pitchShiftSemitones'],0)
