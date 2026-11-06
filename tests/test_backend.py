import sys,pathlib,tempfile,os,json,unittest,types,urllib.error,hashlib
from unittest.mock import patch
PROJECT=pathlib.Path(__file__).resolve().parents[1]
temp=tempfile.TemporaryDirectory();root=pathlib.Path(temp.name)
(root/'backend.json').write_text(json.dumps({'dataDir':str(root),'ffmpeg':sys.executable,'allowedSourceRoots':[str(root/'imports')]}))
os.environ['DSH_SINGING_CONFIG']=str(root/'backend.json');sys.path.insert(0,str(PROJECT/'python'))
import bili_source as b,song_position as p,performance_library as library,runtime
import selection,resolve_song,public_providers

class BackendTests(unittest.TestCase):
 def test_ost_annotation_is_not_mistaken_for_a_different_performance(self):
  self.assertTrue(resolve_song.title_matches('测试曲 (电视剧《虚构剧名》片尾曲)','测试曲'))
  self.assertTrue(resolve_song.title_matches('测试曲（电影《虚构电影》主题曲）','测试曲'))
  for title in ['测试曲 (Live)','测试曲 (DJ版)','测试曲 (Cover)','测试曲 (电视剧《虚构剧名》片尾曲) (Live)','测试曲翻唱 (电视剧《虚构剧名》片尾曲)','其他测试曲 (电视剧《虚构剧名》片尾曲)']:
   self.assertFalse(resolve_song.title_matches(title,'测试曲'))
 def test_verified_recording_lyrics_locate_chorus_without_asr(self):
  lines=[(12,'开头第一句'),(30,'开头第二句'),(70,'重复的副歌甲'),(80,'重复的副歌乙'),(90,'重复的副歌丙'),(100,'重复的副歌丁'),(110,'桥段甲'),(140,'桥段乙'),(190,'重复的副歌甲'),(200,'重复的副歌乙'),(210,'重复的副歌丙'),(220,'重复的副歌丁'),(230,'尾声')]
  metadata={'songId':'fixture'};proof={'method':'verified_recording_correlation','offsetSeconds':.16}
  with patch('lyric_alignment.enrich_lyrics',return_value={**metadata,'lyricLines':lines,'lyricsAlignment':proof}),patch.object(selection,'transcript',side_effect=AssertionError('verified lyrics must not run ASR')):
   start,stop,details=selection.select_range({'mode':'chorus'},'unused',260,metadata,root=root,ffmpeg='unused')
  self.assertEqual((start,stop),(70,110));self.assertEqual(details['lyricsAlignment'],proof)
 def test_point_timestamp_words_are_not_dropped_from_repeated_phrase(self):
  text='测试副歌甲句测试副歌乙句测试副歌丙句';words=[]
  for offset in [40,110]:
   for i,char in enumerate(text):words.append({'text':char,'start':offset+i*.7,'end':offset+i*.7+(0 if i%2 else .6)})
  start,stop=selection.repeated_chorus(words,180)
  self.assertLess(start,41);self.assertGreater(stop,50)
  for word in words:word['end']=word['start']
  with self.assertRaises(p.PositionError):selection.repeated_chorus(words,180)
 def test_each_new_song_lookup_is_independent_of_old_bili_lockout(self):
  import time
  with tempfile.TemporaryDirectory() as folder:
   local=pathlib.Path(folder);state=local/'bilibili-access-cooldown.json'
   state.write_text(json.dumps({'until':time.time()+1800,'reason':'access_denied'}))
   before=state.read_bytes()
   denied=urllib.error.HTTPError('https://api.bilibili.com',412,'denied',{},None)
   wrapped=b.BiliSourceError('B站拒绝本次访问');wrapped.__cause__=denied
   bili=unittest.mock.Mock(side_effect=[wrapped,{'sourceProvider':'bilibili'}])
   providers={'bilibili':bili,'netease':lambda:{'sourceProvider':'netease'}}
   with patch.object(resolve_song,'ROOT',local):
    first=resolve_song.resolve_uncached('Test','Artist',providers=providers)
    second=resolve_song.resolve_uncached('Test','Artist',providers=providers)
   self.assertEqual(first['sourceProvider'],'netease')
   self.assertEqual(first['sourceAttempts'][0]['status'],'access_denied')
   self.assertEqual(second['sourceProvider'],'bilibili')
   self.assertEqual(bili.call_count,2)
   self.assertEqual(state.read_bytes(),before)
 def test_netease_resolver_uses_saved_login_transport(self):
  import io,netease_session
  with patch.object(netease_session,'open_request',return_value=io.BytesIO(b'{"code":200}')) as opening,patch.object(resolve_song.urllib.request,'urlopen',side_effect=AssertionError('anonymous transport')):
   self.assertEqual(resolve_song.get_json('https://music.163.com/api/search/get/web',{'s':'Test'}),{'code':200})
   self.assertEqual(opening.call_args.args[0],resolve_song.ROOT)
 def test_netease_entitled_full_track_is_allowed_but_preview_stays_rejected(self):
  track={'id':123,'name':'Test','duration':180000,'artists':[{'name':'Artist'}]}
  def fetch(url,form=None):
   if '/detail/' in url:return {'songs':[track]}
   if '/player/url' in url:return {'data':[{'code':200,'fee':1,'url':'https://m10.music.126.net/audio.mp3','freeTrialInfo':None}]}
   return {'lrc':{'lyric':''}}
  with patch.object(resolve_song,'get_json',side_effect=fetch),patch.object(resolve_song,'download_full',return_value={'verified':'full'}) as download:
   self.assertEqual(resolve_song.resolve_netease('Test','Artist','https://music.163.com/#/song?id=123'),{'verified':'full'})
   self.assertEqual(download.call_args.args[0]['total'],180)
  preview={'data':[{'code':200,'fee':1,'url':'https://m10.music.126.net/trial.mp3','freeTrialInfo':{'start':0,'end':30000}}]}
  with patch.object(resolve_song,'get_json',side_effect=[{'songs':[track]},preview]),patch.object(resolve_song,'download_full') as download:
   with self.assertRaisesRegex(ValueError,'当前账号'):resolve_song.resolve_netease('Test','Artist','https://music.163.com/song?id=123')
   download.assert_not_called()
 def test_opening_through_chorus_and_long_are_distinct(self):
  lines=[(12,'开头第一句'),(25,'开头第二句'),(40,'开头第三句'),(55,'主歌末句'),(70,'重复的副歌甲'),(80,'重复的副歌乙'),(90,'重复的副歌丙'),(100,'重复的副歌丁'),(110,'桥段甲'),(140,'桥段乙'),(190,'重复的副歌甲'),(200,'重复的副歌乙'),(210,'重复的副歌丙'),(220,'重复的副歌丁'),(230,'尾声')]
  kwargs={'source':'unused','total':260,'metadata':{'songId':'fixture','lyricLines':lines},'root':root,'ffmpeg':'unused'}
  self.assertEqual(selection.select_range({'mode':'opening'},**kwargs)[:2],(12,70))
  self.assertEqual(selection.select_range({'mode':'chorus'},**kwargs)[:2],(70,110))
  self.assertEqual(selection.select_range({'mode':'opening_to_chorus'},**kwargs)[:2],(12,110))
  self.assertEqual(selection.select_range({'mode':'long'},**kwargs)[:2],(12,100))
  self.assertEqual(selection.select_range({'mode':'full'},**kwargs)[:2],(0,260))
 def test_long_does_not_extend_through_chorus_and_opening_has_fallback(self):
  kwargs={'source':'unused','total':300,'metadata':{'songId':'fixture','lyricLines':[(10,'第一句'),(45,'第二句'),(135,'第三句'),(170,'尾句')]},'root':root,'ffmpeg':'unused'}
  with patch.object(resolve_song,'choose_chorus',return_value=(100,'test')),patch.object(resolve_song,'chorus_end',return_value=160):
   self.assertEqual(selection.select_range({'mode':'long'},**kwargs)[:2],(10,100))
  with patch.object(resolve_song,'choose_chorus',side_effect=ValueError('no chorus')):
   self.assertEqual(selection.select_range({'mode':'opening'},**kwargs)[:2],(10,45))
   with self.assertRaises(ValueError):selection.select_range({'mode':'opening_to_chorus'},**kwargs)
 def test_fast_defaults_skip_full_song_transcription(self):
  kwargs={'source':'unused','total':300,'metadata':{'songId':'fixture'},'root':root,'ffmpeg':'unused'}
  with patch.object(selection,'transcript',side_effect=AssertionError('casual excerpt must not transcribe')):
   self.assertEqual(selection.select_range({},**kwargs)[:2],(60,105))
   self.assertEqual(selection.select_range({'mode':'long'},**kwargs)[:2],(60,150))
   self.assertEqual(selection.select_range({'mode':'long','duration':65},**kwargs)[:2],(60,125))
   self.assertEqual(selection.select_range({'mode':'full'},**kwargs)[:2],(0,300))
 def test_structured_modes_reject_conflicting_start(self):
  for mode in ['opening','opening_to_chorus','chorus']:
   with self.assertRaises(ValueError):selection.mode_of({'mode':mode,'start':10,'positionVersion':1})
 def test_new_short_defaults_reject_old_long_cache_but_keep_valid_short_recordings(self):
  with tempfile.TemporaryDirectory() as folder:
   local=pathlib.Path(folder);directory=local/'performance-cache';directory.mkdir()
   audio=directory/('a'*64+'.mp3');audio.write_bytes(b'verified fixture')
   record={'ok':True,'seconds':104.6,'voiceSignature':'test','quality':{'passed':True,'voicedFrames':9000},
     'sourceInfo':{'song':'Test','artist':'Artist','songId':'id','selection':{'softTargetSeconds':120}},
     'requestSpec':{'mode':'long'},'audioSha256':hashlib.sha256(audio.read_bytes()).hexdigest()}
   file=audio.with_suffix('.json');file.write_text(json.dumps(record))
   self.assertIsNone(library.find_performance(local,{'title':'Test','mode':'long'},'test'))
   record['seconds']=82;record['requestSpec']['duration']=90;file.write_text(json.dumps(record))
   self.assertIsNotNone(library.find_performance(local,{'title':'Test','mode':'long'},'test'))
   record['seconds']=39;record['requestSpec']={'mode':'excerpt'};file.write_text(json.dumps(record))
   self.assertIsNotNone(library.find_performance(local,{'title':'Test'},'test'))
 def test_missing_artist_in_title_can_use_description(self):
  self.assertGreater(b.automatic_score({'title':'歌曲《Test》','desc':'演唱：Artist，专辑录音室版本'},'Test','Artist'),0)
  self.assertEqual(b.automatic_score({'title':'歌曲《Test》翻唱','desc':'原唱 Artist'},'Test','Artist'),0)
 def test_explicit_generic_title_does_not_require_singer(self):
  def fetch(url):
   if '/view?' in url:return {'code':0,'data':{'title':'最火俄语歌','duration':150,'cid':123,'pages':[{}],'rights':{}}}
   return {'code':0,'data':{'dash':{'audio':[{'baseUrl':'https://audio.bilivideo.com/fixture'}]}}}
  def run(command,**kwargs):pathlib.Path(command[-1]).write_bytes(b'fixture');return types.SimpleNamespace(returncode=0)
  with tempfile.TemporaryDirectory() as folder:
   result=b.resolve_bili('Test','',source_url='https://www.bilibili.com/video/BV1ozH56tEGb',root=pathlib.Path(folder),fetch=fetch,ffmpeg='unused',run=run,full=True)
   self.assertEqual(result['sourceMatch'],'user_selected_video');self.assertEqual(result['artist'],'视频指定版本')
 def test_alternative_requires_confirmation_before_audio_request(self):
  from source_choice import SourceChoiceRequired
  fetch=unittest.mock.Mock(return_value={'code':0,'data':{'title':'Other singer Test 翻唱','duration':150,'cid':123,'pages':[{}],'rights':{}}})
  with tempfile.TemporaryDirectory() as folder,patch('bili_source.candidates',return_value=['BV1ozH56tEGb']):
   with self.assertRaises(SourceChoiceRequired):b.resolve_bili('Test','Artist',root=pathlib.Path(folder),fetch=fetch,ffmpeg='unused')
  self.assertEqual(fetch.call_count,1)
 def test_explicit_named_cover_is_not_an_automatic_original_match(self):
  title='「雨爱 (司凤版)」';self.assertEqual(b.title_score(title,'雨爱','司凤'),0);self.assertTrue(b.explicit_title_matches(title,'雨爱','司凤'));self.assertFalse(b.explicit_title_matches(title,'雨爱','其他歌手'))
 def test_fake_song_prefix_is_rejected(self):
  self.assertFalse(b.explicit_title_matches('歌手《晴天娃娃》','晴天','歌手'))
 def test_clean_audio_ranked_before_story_mv(self):
  self.assertGreater(b.title_score('Artist《Test》Official Audio','Test','Artist'),b.title_score('Artist《Test》官方 MV','Test','Artist'))
  self.assertEqual(b.title_score('Artist《Test》官方MV剧情版对白','Test','Artist'),0)
 def test_short_link_stays_on_bilibili(self):
  import urllib.request
  for url in ['https://127.0.0.1/video/BV1ozH56tEGb','https://example.com/video/BV1ozH56tEGb','http://www.bilibili.com/video/BV1ozH56tEGb']:
   with self.assertRaises(b.BiliSourceError):b._BiliShortRedirects().redirect_request(urllib.request.Request('https://b23.tv/fixture'),None,302,'Found',{},url)
 def test_combined_audio_video_format(self):
  url='https://audio.bilivideo.com/fixture';self.assertEqual(b.public_audio_url(lambda _:{'code':0,'data':{'durl':[{'url':url}]}},'BV1ozH56tEGb',1),url)
 def test_access_denials_do_not_trigger_bypass(self):
  fetch=unittest.mock.Mock(side_effect=urllib.error.HTTPError('https://api.bilibili.com',403,'denied',{},None))
  with self.assertRaises(b.BiliSourceError):b.public_audio_url(fetch,'BV1ozH56tEGb',1)
  self.assertEqual(fetch.call_count,1)
 def test_preview_rejected(self):
  with self.assertRaises(b.BiliSourceError):b.public_audio_url(lambda _:{'code':0,'data':{'is_preview':True}},'BV1ozH56tEGb',1)
 def test_local_source_roots(self):
  (root/'imports').mkdir(exist_ok=True);good=root/'imports/test.wav';good.write_bytes(b'test');self.assertEqual(runtime.require_source(good),good)
  bad=root/'private.wav';bad.write_bytes(b'test')
  with self.assertRaises(ValueError):runtime.require_source(bad)
 def test_position_zero_and_mutual_exclusion(self):
  self.assertIsNone(p.position_spec());self.assertEqual(p.position_spec(0)['startSeconds'],0)
  with self.assertRaises(p.PositionError):p.position_spec(0,'至少四个字')
 def test_lyric_exact_occurrence(self):
  words=[{'text':'你看见了','start':1,'end':2},{'text':'你看见了','start':10,'end':11}]
  self.assertEqual(p.match_words(words,'你看见了',2)['matchedStartSeconds'],10)
  with self.assertRaises(p.PositionError):p.match_words(words,'不存在的句子')
 def test_time_near_end(self):
  self.assertEqual(p.bounds(10,20,45),(10,20))
  with self.assertRaises(p.PositionError):p.bounds(19,20,45)
 def test_no_ninety_second_limit(self):
  self.assertEqual(p.bounds(20,400,None),(20,400))
  self.assertEqual(p.bounds(0,400,300),(0,300))
  self.assertEqual(selection.mode_of({'mode':'full'}),'full')
  with self.assertRaises(ValueError):selection.mode_of({'mode':'full','duration':45})
 def test_full_and_from_selections(self):
  args={'source':'unused','total':300,'metadata':{'songId':'fixture'},'root':root,'ffmpeg':'unused'}
  self.assertEqual(selection.select_range({'mode':'full'},**args)[:2],(0,300))
  self.assertEqual(selection.select_range({'mode':'from','start':80,'positionVersion':1},**args)[:2],(80,300))
 def test_repeated_chorus_reliable_or_failure(self):
  phrase='这一段足够长的测试文字重复时用来确认范围不能随意截主歌'
  words=[{'text':c,'start':start+i,'end':start+i+.8} for start in (40,100) for i,c in enumerate(phrase)]
  a,z=selection.repeated_chorus(words,180);self.assertAlmostEqual(a,39.88);self.assertGreater(z-a,20)
  with self.assertRaises(ValueError):selection.repeated_chorus(words[:len(phrase)],180)
 def test_provider_order_and_stop(self):
  called=[]
  def provider(name,ok=False):
   def call():
    called.append(name)
    if ok:return {'sourceProvider':name}
    raise ValueError('unavailable')
   return call
  providers={n:provider(n,n=='netease') for n in resolve_song.PROVIDER_ORDER}
  self.assertEqual(resolve_song.resolve_uncached('Test','Artist',providers=providers)['sourceProvider'],'netease')
  self.assertEqual(called,['bilibili','netease'])
 def test_denied_provider_not_retried(self):
  denied=unittest.mock.Mock(side_effect=urllib.error.HTTPError('https://api.bilibili.com',403,'denied',{},None))
  result=resolve_song.resolve_uncached('Test','Artist',providers={'bilibili':denied,'netease':lambda:{'sourceProvider':'netease'}})
  self.assertEqual(denied.call_count,1);self.assertEqual(result['sourceAttempts'][0]['status'],'access_denied')
 def test_explicit_url_never_changes_provider(self):
  called=[]
  def fail():called.append('bili');raise ValueError('denied')
  with self.assertRaises(ValueError):resolve_song.resolve_uncached('Test','Artist','https://www.bilibili.com/video/BV1ozH56tEGb',providers={'bilibili':fail})
  self.assertEqual(called,['bili'])
 def test_qqmusic_public_playback_and_paid_rejection(self):
  track={'title':'Test','singer':[{'name':'Artist'}],'mid':'fixture','file':{'media_mid':'media'},'interval':200,'pay':{'pay_play':0}}
  lookup={'body':{'song':{'list':[track]}}}
  with patch('public_providers.qq_api',side_effect=[lookup,{'midurlinfo':[{'songmid':'fixture','purl':'M500media.mp3'}]}]) as api:
   result=public_providers.resolve_qqmusic('Test','Artist');self.assertEqual(result['total'],200);self.assertEqual(api.call_count,2)
  track['pay']['pay_play']=1
  with patch('public_providers.qq_api',return_value=lookup) as api:
   with self.assertRaises(ValueError):public_providers.resolve_qqmusic('Test','Artist')
   self.assertEqual(api.call_count,1)
 def test_full_cache_rejects_wrong_voice_version_and_corruption(self):
  directory=root/'performance-cache';directory.mkdir(exist_ok=True)
  cache=directory/('a'*64+'.json');master=cache.with_suffix('.master.wav');master.write_bytes(b'master fixture')
  job=root/'jobs/11111111-1111-1111-1111-111111111111';job.mkdir(parents=True,exist_ok=True)
  original=job/'source.wav';original.write_bytes(b'original');vocal=job/'separated/htdemucs/source/vocals.wav';vocal.parent.mkdir(parents=True,exist_ok=True);vocal.write_bytes(b'voice')
  sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
  value={'voiceSignature':'test','quality':{'passed':True},'sourceInfo':{'song':'Test','artist':'Artist','songId':'source:test','sourceComplete':True},'masterSha256':sha(master),'normalizedSha256':sha(original),'vocalSha256':sha(vocal),'job':str(job),'requestSpec':{'source_url':'https://example.invalid/selected'}}
  cache.write_text(json.dumps(value));req={'title':'Test','artist':'Artist','mode':'chorus'}
  self.assertIsNotNone(library.find_full_performance(root,req,'test'))
  self.assertIsNotNone(library.find_full_performance(root,{**req,'artist':''},'test'))
  self.assertIsNone(library.find_full_performance(root,{**req,'artist':'Other'},'test'))
  alternate=directory/('b'*64+'.json');alternate_master=alternate.with_suffix('.master.wav');alternate_master.write_bytes(master.read_bytes())
  alternate.write_text(json.dumps({**value,'sourceInfo':{**value['sourceInfo'],'songId':'source:other','artist':'Other'}}))
  self.assertIsNone(library.find_full_performance(root,{**req,'artist':''},'test'))
  alternate.unlink();alternate_master.unlink()
  self.assertIsNone(library.find_full_performance(root,req,'other'))
  self.assertIsNone(library.find_full_performance(root,{**req,'source_url':'https://example.invalid/other'},'test'))
  master.write_bytes(b'changed');self.assertIsNone(library.find_full_performance(root,req,'test'))
 def test_cache_identity_preserves_start_and_artist(self):
  request={'title':'Same','artist':'A','start':0,'positionVersion':1}
  self.assertEqual(library.request_spec(request)['start'],0)
  self.assertNotEqual(library.request_spec(request),library.request_spec({**request,'artist':'B'}))
 def test_voice_reference_has_no_tts_account_dependency(self):
  from voice_reference import voice_signature
  file=runtime.CONFIG['referenceAudio'];file.parent.mkdir(exist_ok=True);file.write_bytes(b'reference1');first,_=voice_signature();file.write_bytes(b'reference2');second,settings=voice_signature()
  self.assertNotEqual(first,second);self.assertEqual(settings['engine'],'reference_file');self.assertNotIn('api_key',settings)

if __name__=='__main__':unittest.main()
