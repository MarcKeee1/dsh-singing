import sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
import unittest
import numpy as np
from pitch_register import choose_register

class Tests(unittest.TestCase):
    def test_relaxed_reference_does_not_disable_low_song_lift(self):
        source=np.r_[np.full(850,149),np.full(150,195)]
        result=choose_register(source,np.full(1000,194))
        self.assertEqual(result['semitones'],12)
        self.assertEqual(result['reason'],'predominantly_low_singing_register')
    def test_previous_high_reference_lift_is_preserved(self):
        self.assertEqual(choose_register(np.full(1000,149),np.full(1000,247))['semitones'],12)
    def test_high_song_does_not_get_another_octave(self):
        self.assertEqual(choose_register(np.full(1000,385),np.full(1000,194))['semitones'],0)
    def test_normal_register_stays(self):
        self.assertEqual(choose_register(np.full(1000,220),np.full(1000,194))['semitones'],0)
    def test_mixed_low_high_range_not_lifted_wholesale(self):
        source=np.r_[np.full(700,145),np.full(300,300)]
        self.assertEqual(choose_register(source,np.full(1000,194))['semitones'],0)
    def test_scarce_pitch_not_forced(self):
        self.assertEqual(choose_register(np.full(199,140),np.full(1000,194))['reason'],'insufficient_voiced_pitch')
    def test_lower_reference_voice_not_forced(self):
        self.assertEqual(choose_register(np.full(1000,120),np.full(1000,150))['semitones'],0)
    def test_noise_and_nonfinite_frames_are_not_low_notes(self):
        source=np.r_[np.zeros(1500),np.full(1000,300),np.nan,np.inf]
        self.assertEqual(choose_register(source,np.full(1000,194))['semitones'],0)

if __name__=='__main__':unittest.main()
