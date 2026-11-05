import unittest,pathlib,sys,numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
from pitch_register import choose_register
class RegisterTests(unittest.TestCase):
 def test_low_source_lifts_one_octave(self):self.assertEqual(choose_register(np.full(1000,147),np.full(1000,247))['semitones'],12)
 def test_normal_range_unchanged(self):self.assertEqual(choose_register(np.full(1000,225),np.full(1000,247))['semitones'],0)
 def test_insufficient_or_unvoiced_does_not_shift(self):
  for source in [np.zeros(1000),np.full(10,147),np.full(1000,np.nan)]:self.assertEqual(choose_register(source,np.full(1000,247))['semitones'],0)
 def test_few_low_notes_do_not_shift_whole_song(self):self.assertEqual(choose_register(np.r_[np.full(400,147),np.full(600,240)],np.full(1000,247))['semitones'],0)
 def test_high_singer_is_not_lowered(self):self.assertEqual(choose_register(np.full(1000,440),np.full(1000,247))['semitones'],0)
if __name__=='__main__':unittest.main()
