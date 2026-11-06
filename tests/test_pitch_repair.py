import sys,pathlib,unittest,numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
from pitch_repair import octave_masks

class OctaveRepair(unittest.TestCase):
 def test_only_measured_octaves_are_repaired(self):
  m=octave_masks(np.array([300,150,300,300,0,300]),np.array([150,300,280,0,300,75]))
  self.assertEqual(np.flatnonzero(m['up']).tolist(),[0]);self.assertEqual(np.flatnonzero(m['down']).tolist(),[1])
 def test_mismatched_tails_are_bounded(self):
  self.assertEqual(len(octave_masks(np.ones(10)*300,np.ones(8)*150)['up']),8)

if __name__=='__main__':unittest.main()
