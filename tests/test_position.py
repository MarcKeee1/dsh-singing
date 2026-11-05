import json,pathlib,tempfile,types,unittest,hashlib
from unittest.mock import patch
import song_position as p
import bili_source as b
import resolve_song as r
import performance_library as lib
import cover

class PositionTests(unittest.TestCase):
    def test_omission_zero_and_legacy(self):
        self.assertIsNone(p.request_position({'start':0}))
        self.assertIsNone(p.request_position({'start':None,'positionVersion':1}))
        self.assertEqual(p.request_position({'start':0,'positionVersion':1})['startSeconds'],0)
        self.assertEqual(p.position_spec(80)['startSeconds'],80)
    def test_invalid_or_conflicting_positions(self):
        for args in [(0,'小鲸鱼在海里'),(-1,''),(float('nan'),''),(None,'短'),(None,'小鲸鱼在海里',1.5),(None,'',2)]:
            with self.assertRaises(p.PositionError):p.position_spec(*args)
        for start in [266,264]:
            with self.assertRaises(p.PositionError):p.bounds(start,266)
    def words(self):
        return [{'text':char,'start':offset+i*.4,'end':offset+i*.4+.35} for offset in [10,100] for i,char in enumerate('小鲸鱼在海里游泳')]
    def test_actual_word_positions_and_occurrence(self):
        one=p.match_words(self.words(),'小鯨魚在海裡');two=p.match_words(self.words(),'小鲸鱼在海里',2)
        self.assertEqual(one['sourceStartSeconds'],9.88);self.assertEqual(two['sourceStartSeconds'],99.88)
        with self.assertRaises(p.PositionError):p.match_words(self.words(),'小鲸鱼在山上')
        with self.assertRaises(p.PositionError):p.match_words(self.words(),'小鲸鱼在海里',3)
    def test_phrase_cannot_cross_long_silence(self):
        words=self.words()[:9]
        for w in words[3:]:w['start']+=20;w['end']+=20
        with self.assertRaises(p.PositionError):p.match_words(words,'小鲸鱼在海里')
    def test_alignment_timeout_does_not_return_signed_url(self):
        import subprocess
        def run(args,**kw):raise subprocess.TimeoutExpired(args,120)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(p.PositionError) as error:
                p.locate_lyric('https://audio.bilivideo.com/private-signature','https://www.bilibili.com/','fixture',240,'小鲸鱼在海里',1,root=pathlib.Path(temp),ffmpeg='fake',run=run)
            self.assertNotIn('private-signature',str(error.exception))
    def fake_fetch(self,url):
        if '/view?' in url:return {'code':0,'data':{'title':'周杰伦 搁浅 MV','duration':266,'cid':12,'pages':[{}]}}
        return {'code':0,'data':{'dash':{'audio':[{'baseUrl':'https://audio.bilivideo.com/test'}]}}}
    def test_bili_seconds_zero_and_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            calls=[]
            def run(args,**kw):calls.append(args);pathlib.Path(args[-1]).write_bytes(b'audio');return types.SimpleNamespace(returncode=0)
            for start in [0,80,250]:
                row=b.resolve_bili('搁浅','周杰伦',start_seconds=start,root=pathlib.Path(temp),fetch=self.fake_fetch,ffmpeg='fake',run=run)
                self.assertEqual(row['sourceStartSeconds'],start);self.assertEqual(float(calls[-1][calls[-1].index('-ss')+1]),start)
                self.assertEqual(row['seconds'],min(45,266-start));self.assertEqual(row['positionRequest']['mode'],'seconds')
            with self.assertRaises(p.PositionError):b.resolve_bili('搁浅','周杰伦',start_seconds=264,root=pathlib.Path(temp),fetch=self.fake_fetch,ffmpeg='fake',run=run)
            self.assertEqual(len(calls),3)
    def test_bili_lyric_uses_actual_source_not_album_timestamps(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(b,'locate_position',return_value=(112.3,{'method':'actual_audio_word_timestamps'})) as locate:
            def run(args,**kw):pathlib.Path(args[-1]).write_bytes(b'audio');return types.SimpleNamespace(returncode=0)
            row=b.resolve_bili('搁浅','周杰伦',hint='小鲸鱼在海里',lyric_occurrence=2,root=pathlib.Path(temp),fetch=self.fake_fetch,ffmpeg='fake',run=run)
            self.assertEqual(locate.call_args.args[1],'https://audio.bilivideo.com/test')
            self.assertEqual(locate.call_args.args[3],'bili:BV1M4411P7gM:12')
            self.assertEqual(row['positionRequest']['occurrence'],2);self.assertEqual(row['sourceStartSeconds'],112.3)
    def test_known_mv_title_without_spaces(self):
        self.assertGreater(b.title_score('任然MV | 《无人之岛》','无人之岛','任然'),0)
    def test_position_errors_are_not_swallowed_or_rerouted(self):
        with patch.object(r,'resolve_netease',side_effect=p.PositionError('not found')),patch.object(r,'resolve_bili') as fallback:
            with self.assertRaises(p.PositionError):r.resolve_uncached('歌','歌手',hint='找不到的这句')
            fallback.assert_not_called()
    def test_netease_seconds_do_not_depend_on_lyric_or_default_chorus(self):
        track={'id':1,'name':'测试曲','duration':240000,'artists':[{'id':2,'name':'歌手'}]}
        with patch.object(r,'get_json',return_value={'result':{'songs':[track]}}) as fetch,patch.object(r,'resolve_music_source',return_value={'ok':True}) as music,patch.object(r,'select_segment',side_effect=AssertionError('must not choose default')):
            r.resolve_netease('测试曲','歌手',start_seconds=80)
            self.assertEqual(fetch.call_count,1);self.assertEqual(music.call_args.kwargs['position']['startSeconds'],80)
    def test_mv_seconds_not_offset_by_album_alignment(self):
        track={'id':1,'name':'测试曲','duration':240000,'artists':[{'id':2,'name':'歌手'}]}
        responses=[{'data':[{'code':403}]},{'code':200,'data':{'name':'测试曲','artists':[{'id':2,'name':'歌手'}],'duration':243000,'brs':{'480':'https://x.vod.126.net/test'}}}]
        with patch.object(r,'get_json',side_effect=responses),patch.object(r,'extract_positioned',return_value={}) as extract:
            r.resolve_music_source(track,0,45,'test',{'mvId':3,'mvOffset':1.7},position=p.position_spec(80))
            self.assertEqual(extract.call_args.args[-1]['startSeconds'],80);self.assertEqual(extract.call_args.args[3],243)
    def test_public_source_not_cut_twice(self):
        class StopHere(Exception):pass
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);source=root/'input.wav';source.write_bytes(b'x')
            with patch.object(cover,'ROOT',root),patch.object(cover,'MEDIA',root),patch.object(cover,'voice_signature',return_value=('voice',{})),patch.object(cover,'find_performance',return_value=None),patch.object(r,'resolve_public',return_value={'source':str(source),'seconds':20}) as resolve,patch.object(cover.subprocess,'run',side_effect=StopHere) as run:
                with self.assertRaises(StopHere):cover.main({'title':'歌','artist':'歌手','start':80,'positionVersion':1,'duration':20,'output':str(root/'out.mp3')})
                self.assertEqual(resolve.call_args.args[5],80)
                command=run.call_args.args[0];self.assertEqual(command[command.index('-ss')+1],'0')
    def test_library_checks_position_not_only_old_request_hint(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);cache=root/'performance-cache';cache.mkdir();(root/'requests').mkdir()
            audio=cache/('1'*64+'.mp3');audio.write_bytes(b'audio')
            source={'song':'歌','artist':'歌手','songId':'1'}
            rec={'ok':True,'seconds':45,'voiceSignature':'v','quality':{'passed':True,'voicedFrames':3000},'sourceInfo':source,'audioSha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'requestSpec':{'chorus_hint':'小鲸鱼在海里'}}
            meta=audio.with_suffix('.json');meta.write_text(json.dumps(rec),encoding='utf-8')
            request={'title':'歌','artist':'歌手','positionVersion':1,'start':0}
            self.assertIsNone(lib.find_performance(root,request,'v'))
            source['positionRequest']=p.position_spec(0);meta.write_text(json.dumps(rec),encoding='utf-8')
            self.assertIsNotNone(lib.find_performance(root,request,'v'))
            self.assertIsNone(lib.find_performance(root,{**request,'start':80},'v'))
            source['positionRequest']=p.position_spec(None,'小鲸鱼在海里',2);meta.write_text(json.dumps(rec),encoding='utf-8')
            q={**request,'start':None,'chorus_hint':'小鲸鱼在海里'}
            self.assertIsNone(lib.find_performance(root,q,'v'))
            self.assertIsNotNone(lib.find_performance(root,{**q,'lyric_occurrence':2},'v'))

if __name__=='__main__':unittest.main()
