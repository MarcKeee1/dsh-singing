import unittest,numpy as np,pathlib,json,tempfile,hashlib
import soundfile as sf
from unittest.mock import patch
import instrumental_gaps as g

class GapTests(unittest.TestCase):
    def vocal(self):
        rate=1000;wave=np.ones((30000,2))*.04;wave[8000:20000]=0;return wave,rate
    def test_long_internal_instrumental_shortened(self):
        voice,rate=self.vocal();mix=np.ones_like(voice)*.1
        made,plan=g.edit_mix(mix,voice,rate)
        self.assertEqual(len(plan['cuts']),1);self.assertGreater(plan['removedSeconds'],9)
        a,b=plan['cuts'][0];self.assertGreater(a,8);self.assertLess(b,20)
        self.assertTrue(np.allclose(made,.1));self.assertGreater(len(made)/rate,18)
    def test_breaths_and_short_rest_stay(self):
        voice,rate=self.vocal();voice[:]=.04;voice[8000:12000]=0
        made,plan=g.edit_mix(voice,voice,rate);self.assertEqual(plan['cuts'],[]);self.assertEqual(len(made),len(voice))
    def test_quiet_singing_and_stereo_phase_preserved(self):
        voice,rate=self.vocal();voice[:]=.0003;voice[:,1]*=-1
        self.assertEqual(g.plan_gaps(voice,rate)['cuts'],[])
    def test_start_and_end_short_pause_kept(self):
        voice,rate=self.vocal();voice[:]=.04;voice[:10000]=0;voice[22000:]=0
        cuts=g.plan_gaps(voice,rate)['cuts'];self.assertEqual(len(cuts),2)
        self.assertGreaterEqual(cuts[0][0],.6);self.assertLess(cuts[-1][-1],30)
    def test_old_cached_performance_upgraded_without_resynthesis(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);job=root/'jobs'/'test';stems=job/'separated/htdemucs/source';stems.mkdir(parents=True)
            raw,rate=self.vocal();sf.write(stems/'vocals.wav',raw,rate);sf.write(stems/'no_vocals.wav',np.ones_like(raw)*.1,rate)
            (job/'converted').mkdir();sf.write(job/'converted/voice.wav',raw,rate)
            audio=root/'cached.mp3';audio.write_bytes(b'old')
            record={'seconds':30,'job':str(job),'audioSha256':hashlib.sha256(audio.read_bytes()).hexdigest()}
            def encode(args,**kw):pathlib.Path(args[-1]).write_bytes(b'edited');return type('Result',(),{'returncode':0})()
            with patch.object(g.subprocess,'run',side_effect=encode) as worker:
                target,edited=g.cached_edited(audio,record,root,'ffmpeg');self.assertEqual(worker.call_count,1)
                second,same=g.cached_edited(audio,record,root,'ffmpeg');self.assertEqual(worker.call_count,1)
            self.assertLess(edited['seconds'],21);self.assertEqual(edited['gapEditVersion'],1);self.assertEqual(edited,same);self.assertEqual(target,second)
            self.assertEqual(audio.read_bytes(),b'old')

if __name__=='__main__':unittest.main()
