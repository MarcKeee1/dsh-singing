import pathlib,json,unittest,numpy as np,hashlib,tempfile
from unittest.mock import patch
import soundfile as sf
from singing_mix import mix_tracks
from instrumental_gaps import cached_edited

class MixTests(unittest.TestCase):
    def test_relative_vocal_level_and_no_pitch_change(self):
        rate=8000;t=np.arange(16000)/rate
        voice=(.1*np.sin(2*np.pi*400*t))[:,None];music=np.repeat((.1*np.sin(2*np.pi*900*t))[:,None],2,axis=1)
        mix,settings=mix_tracks(voice,music,voice,rate)
        sample=mix[4000:12000,0];fft=np.abs(np.fft.rfft(sample))
        self.assertAlmostEqual(20*np.log10(fft[400]/fft[900]),7.13,places=2)
        self.assertEqual(len(mix),len(music));self.assertEqual(settings['version'],2)
    def test_loud_stems_do_not_clip(self):
        raw=np.ones((80000,2))*3
        mix,settings=mix_tracks(raw,raw,raw,8000)
        self.assertLessEqual(np.max(np.abs(mix)),.89001);self.assertTrue(np.isfinite(mix).all())
    def test_cached_mix_rebuilt_once_and_original_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);job=root/'jobs'/'fixture';stems=job/'separated/htdemucs/source';stems.mkdir(parents=True);(job/'converted').mkdir()
            rate=8000;voice=np.ones((160000,2))*.04;voice[70000:]=0;music=np.ones_like(voice)*.1
            sf.write(stems/'vocals.wav',voice,rate);sf.write(stems/'no_vocals.wav',music,rate);sf.write(job/'converted/voice.wav',voice,rate)
            source=root/'old.mp3';source.write_bytes(b'original')
            record={'seconds':20,'job':str(job),'audioSha256':hashlib.sha256(source.read_bytes()).hexdigest()}
            def encode(args,**kw):pathlib.Path(args[-1]).write_bytes(b'balanced');return type('Result',(),{'returncode':0})()
            with patch('instrumental_gaps.subprocess.run',side_effect=encode) as run:
                audio,result=cached_edited(source,record,root,'ffmpeg');again,second=cached_edited(source,record,root,'ffmpeg')
                self.assertEqual(run.call_count,1)
            self.assertEqual(result['mixVersion'],2);self.assertGreater(result['gapEdits']['removedSeconds'],5)
            self.assertEqual(audio,again);self.assertEqual(result,second);self.assertEqual(source.read_bytes(),b'original')

if __name__=='__main__':unittest.main()
