import unittest,pathlib,tempfile,json,urllib.error,types,hashlib
from unittest.mock import patch
import resolve_song as r
import bili_source as b
import performance_library as library
from song_position import PositionError

class SourceTests(unittest.TestCase):
    def test_jay_bypasses_netease_for_all_aliases(self):
        for artist in ['周杰伦','周杰倫','Jay Chou','周杰倫 Jay Chou']:
            with patch.object(r,'resolve_netease',side_effect=AssertionError('NetEase must not run')),patch.object(r,'resolve_bili',return_value={'artist':'周杰伦'}) as direct:
                self.assertEqual(r.resolve_uncached('搁浅',artist)['artist'],'周杰伦');self.assertEqual(direct.call_args.args[1],'周杰伦')
    def test_netease_empty_and_unavailable_fall_back_without_changing_artist(self):
        for error in [ValueError('no catalog'),urllib.error.HTTPError('https://music.163.com/api/search',503,'Unavailable',{},None)]:
            with patch.object(r,'resolve_netease',side_effect=error),patch.object(r,'resolve_bili',return_value={'ok':True}) as fallback:
                r.resolve_uncached('歌名','原歌手');self.assertEqual(fallback.call_args.args[:2],('歌名','原歌手'))
    def test_bili_block_is_not_retried_by_another_route(self):
        with patch.object(r,'resolve_netease',side_effect=b.BiliSourceError('blocked')),patch.object(r,'resolve_bili') as fallback:
            with self.assertRaises(b.BiliSourceError):r.resolve_uncached('歌名','歌手')
            fallback.assert_not_called()
    def test_explicit_bv_skips_netease(self):
        with patch.object(r,'resolve_netease',side_effect=AssertionError()),patch.object(r,'resolve_bili',return_value={}) as direct:
            r.resolve_uncached('测试','歌手',source_url='https://www.bilibili.com/video/BV1M4411P7gM');direct.assert_called_once()
    def test_title_performer_and_version(self):
        self.assertGreater(b.title_score('【周杰倫】蒲公英的約定 MV 高画质','蒲公英的约定','周杰伦'),0)
        self.assertGreater(b.title_score('周杰倫 Jay Chou【擱淺】Official MV','搁浅','Jay Chou'),0)
        for title in ['林俊杰《搁浅》MV','周杰伦《搁浅的船》MV','周杰伦《搁浅》翻唱','周杰伦《搁浅》AI翻唱','周杰伦《搁浅》伴奏','周杰伦《搁浅》Live','周杰伦《搁浅》降调版']:
            self.assertEqual(b.title_score(title,'搁浅','周杰伦'),0,title)
        self.assertFalse(r.artist_matches('周深-','周深'))
    def test_non_official_uploader_mv_can_be_candidate(self):
        result={'code':0,'data':{'result':[{'bvid':'BV1eb411V7BA','title':'周杰伦 蒲公英的约定 MV','author':'普通上传者','duration':'4:0','play':100}]}}
        self.assertEqual(b.candidates('蒲公英的约定','周杰伦','',lambda url:result),['BV1eb411V7BA'])
    def test_invalid_links_are_rejected(self):
        for link in ['http://www.bilibili.com/video/BV1M4411P7gM','https://evil.com/video/BV1M4411P7gM','https://www.bilibili.com/video/BV1M4411P7gM?p=2']:
            with self.assertRaises(b.BiliSourceError):b.parse_bvid(link)
    def test_independent_source_download_cache_and_hint_honesty(self):
        with tempfile.TemporaryDirectory() as temp:
            root=pathlib.Path(temp);calls=[]
            def fetch(url):
                self.assertNotIn('163.com',url);calls.append(url)
                if '/view?' in url:return {'code':0,'data':{'title':'周杰伦 搁浅 MV','duration':266,'cid':12,'pages':[{}],'owner':{'name':'上传者'}}}
                return {'code':0,'data':{'dash':{'audio':[{'baseUrl':'https://audio.bilivideo.com/allowed','bandwidth':100}]}}}
            def run(args,**kwargs):pathlib.Path(args[-1]).write_bytes(b'fixture-audio');return types.SimpleNamespace(returncode=0)
            one=b.resolve_bili('搁浅','周杰伦',root=root,fetch=fetch,ffmpeg='fake',run=run)
            self.assertEqual(one['artist'],'周杰伦');self.assertEqual(one['seconds'],45);self.assertFalse(one['timelineAligned'])
            second=b.resolve_bili('搁浅','周杰伦',root=root,fetch=fetch,ffmpeg='fake',run=lambda *a,**k:self.fail('No second download'))
            self.assertEqual(one,second)
            with patch.object(b,'locate_position',side_effect=PositionError('未找到指定起句')),self.assertRaisesRegex(PositionError,'起句'):b.resolve_bili('搁浅','周杰伦',hint='指定起句',root=root,fetch=fetch,ffmpeg='fake',run=run)
    def test_fake_media_domain_is_not_downloaded(self):
        def fetch(url):
            if '/view?' in url:return {'code':0,'data':{'title':'周杰伦 搁浅 MV','duration':266,'cid':12}}
            return {'code':0,'data':{'dash':{'audio':[{'baseUrl':'https://evil.com/audio'}]}}}
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(b.BiliSourceError,'域名'):b.resolve_bili('搁浅','周杰伦',root=pathlib.Path(temp),fetch=fetch,ffmpeg='fake',run=lambda *a,**k:self.fail('No download'))
    def test_cached_sources_reuse_offline_with_jay_alias(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(r,'ROOT',pathlib.Path(temp)):
            directory=pathlib.Path(temp)/'song-cache';directory.mkdir()
            audio=directory/'fixture.wav';audio.write_bytes(b'synthetic source')
            record={'artist':'周杰伦','source':str(audio),'seconds':45,'sha256':hashlib.sha256(audio.read_bytes()).hexdigest()}
            for song in ['搁浅','蒲公英的约定']:
                with patch.object(r,'resolve_uncached',return_value=record):r.resolve_public(song,'周杰伦')
                with patch.object(r,'get_json',side_effect=AssertionError('No network')),patch.object(r,'resolve_uncached',side_effect=AssertionError('No source lookup')):
                    cached=r.resolve_public(song,'Jay Chou');self.assertEqual(cached['artist'],'周杰伦');self.assertTrue(r.valid_cache(cached))
    def test_old_non_jay_cache_remains_offline(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(r,'ROOT',pathlib.Path(temp)):
            directory=pathlib.Path(temp)/'song-cache';directory.mkdir()
            audio=directory/'fixture.wav';audio.write_bytes(b'synthetic source')
            record={'artist':'任然','source':str(audio),'seconds':45,'sha256':hashlib.sha256(audio.read_bytes()).hexdigest()}
            with patch.object(r,'resolve_uncached',return_value=record):r.resolve_public('无人之岛','任然')
            with patch.object(r,'get_json',side_effect=AssertionError('No network')),patch.object(r,'resolve_uncached',side_effect=AssertionError('No source lookup')):
                self.assertTrue(r.valid_cache(r.resolve_public('无人之岛','任然')))

if __name__=='__main__':unittest.main()
