import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np
import soundfile as sf

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
import lyric_alignment as alignment


class LyricAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        (self.root/'song-cache').mkdir()
        self.rate=4000
        rng=np.random.default_rng(24901)
        self.audio=np.convolve(rng.normal(0,.1,60*self.rate),np.ones(3)/3,mode='same').astype('float32')
        self.reference=self.root/'song-cache/reference.wav'
        self.source=self.root/'selected.wav'
        sf.write(self.reference,self.audio,self.rate,subtype='FLOAT')
        shifted=np.concatenate([np.zeros(1200,dtype='float32'),self.audio*.7])
        sf.write(self.source,shifted,self.rate,subtype='FLOAT')
        self.metadata={'song':'Fixture','artist':'Artist','songId':'bili:fixture','sourceProvider':'bilibili','source':str(self.source)}
        self.record={'song':'Fixture','artist':'Artist','songId':'netease:fixture','sourceProvider':'netease',
                     'sourceComplete':True,'source':str(self.reference),'sha256':alignment.digest(self.reference),
                     'seconds':60,'lyricLines':[(10,'测试第一句'),(20,'测试第二句'),(30,'测试第三句'),(40,'测试第四句')]}

    def test_three_independent_windows_establish_offset_despite_gain(self):
        result=alignment.align_recordings(self.source,self.reference)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['offsetSeconds'],.3,places=2)
        self.assertEqual(len(result['matchedWindows']),3)
        self.assertGreater(min(w['correlation'] for w in result['matchedWindows']),.98)

    def test_negative_offset_is_supported(self):
        sf.write(self.source,self.audio[1200:],self.rate,subtype='FLOAT')
        result=alignment.align_recordings(self.source,self.reference)
        self.assertAlmostEqual(result['offsetSeconds'],-.3,places=2)

    def test_different_recording_and_inserted_break_are_not_treated_as_aligned(self):
        sf.write(self.source,np.random.default_rng(999).normal(0,.1,len(self.audio)),self.rate,subtype='FLOAT')
        self.assertIsNone(alignment.align_recordings(self.source,self.reference))
        shifted=np.concatenate([self.audio[:30*self.rate],np.zeros(self.rate),self.audio[30*self.rate:]])
        sf.write(self.source,shifted,self.rate,subtype='FLOAT')
        self.assertIsNone(alignment.align_recordings(self.source,self.reference))

    def test_enrichment_preserves_source_and_reuses_verified_disk_result(self):
        fetch=Mock(return_value=self.record)
        result=alignment.enrich_lyrics(self.source,60.3,self.metadata,root=self.root,fetch_reference=fetch)
        self.assertAlmostEqual(result['lyricLines'][0][0],10.3,places=2)
        self.assertEqual(result['source'],self.metadata['source'])
        self.assertEqual(result['songId'],'bili:fixture')
        again=alignment.enrich_lyrics(self.source,60.3,self.metadata,root=self.root,
                                     fetch_reference=Mock(side_effect=AssertionError('cached result must not access network')))
        self.assertEqual(result,again)
        fetch.assert_called_once_with('Fixture','Artist')

    def test_reference_identity_hash_duration_and_path_are_checked(self):
        for key,value in [('artist','Other'),('song','Other'),('sourceComplete',False),('sha256','bad'),('seconds',20)]:
            record={**self.record,key:value}
            result=alignment.enrich_lyrics(self.source,60.3,self.metadata,root=self.root,fetch_reference=Mock(return_value=record))
            self.assertNotIn('lyricLines',result)
        other=self.root/'outside.wav';other.write_bytes(self.reference.read_bytes())
        result=alignment.enrich_lyrics(self.source,60.3,self.metadata,root=self.root,
                                      fetch_reference=Mock(return_value={**self.record,'source':str(other)}))
        self.assertNotIn('lyricLines',result)

    def test_changed_selected_audio_invalidates_the_old_alignment(self):
        alignment.enrich_lyrics(self.source,60.3,self.metadata,root=self.root,fetch_reference=Mock(return_value=self.record))
        sf.write(self.source,np.random.default_rng(1).normal(0,.1,round(60.3*self.rate)),self.rate,subtype='FLOAT')
        result=alignment.enrich_lyrics(self.source,60.3,self.metadata,root=self.root,fetch_reference=Mock(side_effect=AssertionError('reference cached')))
        self.assertNotIn('lyricLines',result)

    def test_existing_lyrics_local_sources_and_unavailable_reference_keep_old_path(self):
        for metadata in [dict(self.metadata,lyricLines=[(10,'现有时间轴')]),dict(self.metadata,sourceProvider='local'),dict(self.metadata,artist='')]:
            fetch=Mock(side_effect=AssertionError('must not query reference'))
            self.assertEqual(alignment.enrich_lyrics(self.source,60.3,metadata,root=self.root,fetch_reference=fetch),metadata)
            fetch.assert_not_called()
        result=alignment.enrich_lyrics(self.source,60.3,self.metadata,root=self.root,
                                      fetch_reference=Mock(side_effect=ValueError('no reference')))
        self.assertEqual(result,self.metadata)

    def test_corrupt_cached_evidence_is_recomputed_and_reference_timeout_falls_back(self):
        import subprocess
        alignment.enrich_lyrics(self.source,60.3,self.metadata,root=self.root,fetch_reference=Mock(return_value=self.record))
        file=next((self.root/'lyric-alignment-cache').glob('*.json'))
        data=json.loads(file.read_text('utf-8'));data['lyricsAlignment']['matchedWindows'][0]['correlation']=.1
        file.write_text(json.dumps(data),'utf-8')
        from unittest.mock import patch
        with patch.object(alignment,'align_recordings',wraps=alignment.align_recordings) as run:
            fixed=alignment.enrich_lyrics(self.source,60.3,self.metadata,root=self.root,fetch_reference=Mock(side_effect=AssertionError('reference cached')))
        run.assert_called_once();self.assertTrue(alignment.valid_alignment(fixed['lyricsAlignment']))
        with tempfile.TemporaryDirectory() as folder:
            result=alignment.enrich_lyrics(self.source,60.3,self.metadata,root=pathlib.Path(folder),
                                          fetch_reference=Mock(side_effect=subprocess.TimeoutExpired('ffmpeg',20)))
            self.assertEqual(result,self.metadata)


if __name__=='__main__':
    unittest.main()
