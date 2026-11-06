import pathlib,sys,unittest,numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
from phrase_register import plan,apply,local_quality

class PhraseRegister(unittest.TestCase):
 def test_low_song_high_phrases_do_not_get_double_lift(self):
  f=np.full(6000,148.);f[3200:3270]=258;f[5870:5950]=294
  p=plan(f,np.full(1400,227.),12);e=apply(f,p,12)
  self.assertEqual([(x['startFrame'],x['endFrame']) for x in p['intervals']],[(3200,3270),(5870,5950)])
  self.assertEqual(e[100],296);self.assertEqual(e[3220],258);self.assertEqual(e[5900],294)
 def test_harmony_is_checked_independently(self):
  f=np.full(1200,132.);f[450:550]=260
  p=plan(f,np.full(1400,227.),12)
  self.assertEqual(apply(f,p,12)[500],260)
 def test_zero_shift_and_disabled_auto_keep_high_notes(self):
  f=np.full(1000,450.)
  p=plan(f,np.full(1000,227.),0)
  np.testing.assert_array_equal(apply(f,p,0),f)
 def test_tiny_outlier_is_not_an_octave_switch(self):
  f=np.full(1000,145.);f[400:405]=220
  self.assertFalse(plan(f,np.full(1000,227.),12)['intervals'])
 def test_vibrato_uses_hysteresis(self):
  f=np.r_[np.full(100,150.),np.tile([220.,210.],20),np.full(100,150.)]
  p=plan(f,np.full(1000,227.),12)
  self.assertEqual(len(p['intervals']),1)
 def test_low_note_breaks_high_phrase_and_silence_stays_silent(self):
  f=np.r_[np.full(30,260.),np.zeros(3),np.full(30,260.),np.full(5,130.),np.full(30,260.)]
  p=plan(f,np.full(1000,227.),12);e=apply(f,p,12)
  self.assertEqual(len(p['intervals']),2);self.assertEqual(e[31],0);self.assertEqual(e[64],260)
 def test_profile_cannot_disable_shift_outside_track(self):
  f=np.full(1000,150.);p=plan(f,np.full(1000,227.),12);p['intervals']=[{'startFrame':0,'endFrame':1001,'semitones':0}]
  with self.assertRaises(ValueError):apply(f,p,12)
 def test_nonfinite_pitch_and_mismatched_profiles_fail(self):
  with self.assertRaises(ValueError):plan([np.nan],np.ones(300)*227,12)
  with self.assertRaises(ValueError):apply(np.ones(1000)*150,plan(np.ones(1000)*150,np.ones(1000)*227,12),0)
 def test_missing_reference_does_not_guess_a_ceiling(self):
  self.assertFalse(plan(np.ones(1000)*260,np.zeros(1000),12)['intervals'])
 def test_tiny_backing_phrase_does_not_invent_accuracy(self):
  q=local_quality({'passed':False,'reason':'not_enough_voiced_frames','voicedFrames':17})
  self.assertFalse(q['assessed']);self.assertIsNone(q['passed'])
 def test_local_pitch_gate_still_rejects_an_octave(self):
  q=local_quality({'voicedFrames':35,'voicedCoverage':.8,'medianAbsoluteCents':1200,'p90AbsoluteCents':1210})
  self.assertTrue(q['assessed']);self.assertFalse(q['passed'])
 def test_local_pitch_is_independent_of_track_coverage(self):
  q=local_quality({'voicedFrames':78,'voicedCoverage':.7429,'medianAbsoluteCents':16,'p90AbsoluteCents':49})
  self.assertTrue(q['passed']);self.assertTrue(q['coverageCheckedAtTrackLevel'])
 def test_low_phrases_are_lifted_even_when_whole_song_base_is_zero(self):
  f=np.r_[np.full(400,194.),np.zeros(25),np.full(400,148.),np.zeros(25),np.full(400,260.)]
  p=plan(f,np.full(1000,227.),0);e=apply(f,p,0)
  self.assertEqual(e[100],388);self.assertEqual(e[500],296);self.assertEqual(e[1000],260)
 def test_disabling_auto_preserves_low_phrases(self):
  f=np.full(1000,148.);p=plan(f,np.full(1000,227.),0,enabled=False);np.testing.assert_array_equal(apply(f,p,0),f)
 def test_legacy_high_protection_profile_remains_readable(self):
  p={'version':1,'baseShiftSemitones':12,'frameRate':100,'intervals':[{'startFrame':200,'endFrame':300,'semitones':0}]}
  f=np.full(1000,260.);self.assertEqual(apply(f,p,12)[250],260)
 def test_short_extreme_harmonic_cannot_be_doubled_to_squeal(self):
  f=np.full(1000,150.);f[400:403]=465.
  p=plan(f,np.full(1000,227.),0);self.assertEqual(apply(f,p,0)[401],465)

if __name__=='__main__':unittest.main()
