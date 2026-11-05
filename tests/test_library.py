import hashlib,json,pathlib,tempfile,unittest,sys
from unittest.mock import patch
import performance_library as lib
import cover


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.tmp.name)
        (self.root/'performance-cache').mkdir()
        (self.root/'requests').mkdir()
        self.query={'title':'雨爱','artist':'杨丞琳','duration':None,'start':0}
        self.add()
    def tearDown(self):self.tmp.cleanup()
    def add(self,number=1,**updates):
        stem=f'{number:064x}'
        audio=self.root/'performance-cache'/(stem+'.mp3');audio.write_bytes(b'verified performance'+str(number).encode())
        record={'ok':True,'seconds':45,'voiceSignature':'voice-1','quality':{'passed':True,'voicedFrames':3000},
                'sourceInfo':{'song':'雨爱','artist':'杨丞琳','songId':'316100','chorusMethod':'complete_section'},
                'audioSha256':hashlib.sha256(audio.read_bytes()).hexdigest(),**updates}
        (self.root/'performance-cache'/(stem+'.json')).write_text(json.dumps(record),encoding='utf-8')
    def find(self,**q):return lib.find_performance(self.root,{**self.query,**q},'voice-1')
    def test_song_artist_normalization_and_omitted_artist(self):
        self.assertIsNotNone(self.find(title='《雨爱》',artist=' 杨 丞琳 '));self.assertIsNotNone(self.find(artist=''))
    def test_wrong_song_or_artist_never_reused(self):
        self.assertIsNone(self.find(title='无人之境'));self.assertIsNone(self.find(artist='任然'))
    def test_new_voice_is_a_miss(self):self.assertIsNone(lib.find_performance(self.root,self.query,'voice-2'))
    def test_changed_duration_is_not_silently_ignored(self):
        self.assertIsNone(self.find(duration=20));self.assertIsNotNone(self.find(duration=45))
    def test_earlier_lyric_boundary_requires_matching_request(self):
        self.add(seconds=18,requestSpec={'duration':20});self.assertIsNotNone(self.find(duration=20));self.assertIsNone(self.find(duration=30))
    def test_hint_and_source_require_exact_provenance(self):
        self.assertIsNone(self.find(chorus_hint='给定起点'));self.assertIsNone(self.find(source_url='https://example.org/source'))
        self.add(sourceInfo={'song':'雨爱','artist':'杨丞琳','songId':'316100','positionRequest':lib.request_position({'chorus_hint':'给定起点'})},requestSpec={'chorus_hint':'给定起点','source_url':'https://example.org/source'})
        self.assertIsNotNone(self.find(chorus_hint='给定起点'));self.assertIsNotNone(self.find(source_url='https://example.org/source'))
    def test_local_import_and_explicit_start_not_replaced(self):
        self.assertIsNone(self.find(source='import.wav'));self.assertIsNone(self.find(start=20))
    def test_longest_completed_recording_preferred(self):
        self.add(number=2,seconds=60);self.assertEqual(self.find()[1]['seconds'],60)
    def test_conflicting_performers_not_silently_picked(self):
        self.add(number=2,sourceInfo={'song':'雨爱','artist':'另一位','songId':'999'})
        self.assertIsNone(self.find(artist=''));self.assertIsNotNone(self.find())
    def test_corrupt_or_failed_audio_rejected(self):
        self.add(quality={'passed':False,'voicedFrames':3000});self.assertIsNone(self.find())
        self.add(quality={'passed':True,'voicedFrames':5});self.assertIsNone(self.find())
        self.add(audioSha256='changed');self.assertIsNone(self.find())
        (self.root/'performance-cache'/f'{1:064x}.json').write_text('{bad');self.assertIsNone(self.find())
    def test_legacy_request_provenance_is_read_without_arbitrary_paths(self):
        uuid='11111111-1111-1111-1111-111111111111'
        (self.root/'requests'/(uuid+'.json')).write_text(json.dumps({'chorus_hint':'给定起点'}),encoding='utf-8')
        self.add(path='C:/Users/Example/.dsh/media/onebot/voice/sing-'+uuid+'.mp3')
        self.assertIsNone(self.find(chorus_hint='给定起点'))
    def test_title_artist_hint_do_not_depend_on_lookup_cache_keys(self):
        self.add(sourceInfo={'song':'LOSER','artist':'米津玄師','songId':'512359195','positionRequest':lib.request_position({'chorus_hint':"I'm a loser"})},requestSpec={'chorus_hint':"I'm a loser"})
        self.assertIsNotNone(self.find(title='ｌｏｓｅｒ',artist='米津玄師',chorus_hint="I’m a loser"))
    def test_invalid_length_and_nan_rejected(self):
        for sec in [float('nan'),0,100]:self.add(seconds=sec);self.assertIsNone(self.find())

class FinishedCachePipelineTests(unittest.TestCase):
    def test_existing_rain_recording_works_with_network_and_workers_forbidden(self):
        # A synthetic finished recording keeps this test independent of private audio.
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);out=root/'media';out.mkdir();cache=root/'performance-cache';cache.mkdir()
            audio=cache/('1'*64+'.mp3');audio.write_bytes(b'synthetic finished recording')
            digest=hashlib.sha256(audio.read_bytes()).hexdigest()
            record={'ok':True,'seconds':45,'voiceSignature':'test-voice','quality':{'passed':True,'voicedFrames':3000},
                    'sourceInfo':{'song':'雨爱','artist':'杨丞琳','songId':'fixture'},'audioSha256':digest,
                    'gapEditVersion':1,'mixVersion':2}
            audio.with_suffix('.json').write_text(json.dumps(record),encoding='utf-8')
            with patch.object(cover,'ROOT',root),patch.object(cover,'MEDIA',out),patch.object(cover,'voice_signature',return_value=('test-voice',{})),patch.object(cover.subprocess,'run',side_effect=AssertionError('No worker allowed')),patch('resolve_song.resolve_public',side_effect=AssertionError('No source lookup allowed')):
                q={'title':'雨爱','artist':'杨丞琳','output':str(out/'cached-rain.mp3'),'duration':None,'start':0}
                a=cover.main(q,cache_only=True);b=cover.main({**q,'artist':'','output':str(out/'cached-rain-repeat.mp3')},cache_only=True)
                self.assertTrue(a['cacheHit']);self.assertTrue(b['cacheHit']);self.assertEqual(a['cacheMode'],'performance_library')
                self.assertEqual(hashlib.sha256((out/'cached-rain.mp3').read_bytes()).hexdigest(),a['audioSha256'])
                self.assertEqual(a['audioSha256'],b['audioSha256'])
                miss=cover.main({**q,'title':'__not_a_cached_song__'},cache_only=True);self.assertTrue(miss['cacheMiss'])

if __name__=='__main__':unittest.main()
