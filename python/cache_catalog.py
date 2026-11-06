"""Verified, public-source recordings that can be played without a model or network."""
import hashlib,json,math,pathlib,re,shutil,urllib.parse,time,html,unicodedata
import soundfile as sf

PAGE_SIZE=12
PUBLIC_HOSTS={'www.bilibili.com','bilibili.com','music.163.com','y.qq.com'}

def clean(value,limit):
    return re.sub(r'[\x00-\x1f\x7f]+',' ',str(value or '')).strip()[:limit]

def verified(root,cache_id,max_bytes=20*1024*1024):
    if not re.fullmatch('[0-9a-f]{64}',str(cache_id)):raise ValueError('缓存歌曲编号无效')
    directory=(pathlib.Path(root)/'performance-cache').resolve()
    meta=directory/(cache_id+'.json');audio=directory/(cache_id+'.mp3')
    if meta.is_symlink() or audio.is_symlink() or not meta.is_file() or not audio.is_file():raise ValueError('缓存歌曲已不存在')
    if meta.stat().st_size>256*1024 or not 0<audio.stat().st_size<=max_bytes:raise ValueError('缓存文件不适合发送')
    record=json.loads(meta.read_text(encoding='utf-8'));source=record.get('sourceInfo') or {};quality=record.get('quality') or {}
    # Local imports can contain private recordings. Do not expose them through
    # a shared group catalog merely because their cache filename is known.
    page=urllib.parse.urlparse(str(source.get('sourcePage') or ''))
    if page.scheme!='https' or page.hostname not in PUBLIC_HOSTS or source.get('sourceProvider')=='local' or str(source.get('songId','')).startswith('local:'):
        raise ValueError('这条录音不在可共享的缓存歌单中')
    seconds=float(record.get('seconds',0));title=clean(source.get('song'),160);artist=clean(source.get('artist'),80)
    if record.get('ok') is not True or quality.get('passed') is not True or not title or not artist or not source.get('songId') or not math.isfinite(seconds) or seconds<5 or quality.get('voicedFrames',0)<200:
        raise ValueError('缓存歌曲未通过质量检查')
    if hashlib.sha256(audio.read_bytes()).hexdigest()!=record.get('audioSha256'):raise ValueError('缓存歌曲已损坏')
    actual=sf.info(audio).duration
    if actual<5 or abs(actual-seconds)>max(.5,seconds*.01):raise ValueError('缓存音频不完整')
    return audio,record,{'cacheId':cache_id,'song':title,'artist':artist,'seconds':round(actual,2),
        'segment':'整首' if source.get('sourceComplete') else ('完整副歌' if 'complete_section' in source.get('chorusMethod','') else '片段'),
        'startSeconds':source.get('sourceStartSeconds',source.get('chorusStartSeconds'))}

def catalog(root,signature=None,offset=0,max_bytes=20*1024*1024):
    if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:raise ValueError('歌单分页位置无效')
    directory=pathlib.Path(root)/'performance-cache';selected={};valid_count=0
    identity_text=lambda value: re.sub(r'\s+','',unicodedata.normalize('NFKC',html.unescape(value))).casefold()
    for meta in directory.glob('*.json'):
        try:
            audio,record,item=verified(root,meta.stem,max_bytes)
            valid_count+=1
            sig=record.get('voiceSignature')
            item['voice']='当前音色' if signature and sig==signature else '以前保存的音色'
            # The menu shows one long recording per song/artist. Other versions
            # remain available to exact source/position requests and cache IDs.
            identity=(identity_text(item['song']),identity_text(item['artist']))
            rank=(item['seconds'],sig==signature,item['segment']=='整首',meta.stat().st_mtime)
            if identity not in selected or rank>selected[identity][0]:selected[identity]=(rank,item)
        except (OSError,ValueError,TypeError,KeyError,AttributeError,RuntimeError):continue
    items=sorted((row[1] for row in selected.values()),key=lambda x:(-x['seconds'],x['song'].casefold(),x['artist'].casefold(),x['cacheId']))
    page=[{**item,'number':offset+i+1} for i,item in enumerate(items[offset:offset+PAGE_SIZE])]
    return {'ok':True,'kind':'cached_song_catalog','total':len(items),'offset':offset,'items':page,
        'hiddenCount':valid_count-len(items),
        'nextOffset':offset+len(page) if offset+len(page)<len(items) else None}

def materialize(root,cache_id,output,signature=None,max_bytes=20*1024*1024):
    started=time.monotonic()
    audio,record,item=verified(root,cache_id,max_bytes)
    output=pathlib.Path(output);output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(audio,output)
    # The caller must fence outputDir; this helper never accepts a source path.
    return {**record,'ok':True,'path':str(output),'seconds':item['seconds'],'song':item['song'],
        'cacheHit':True,'cacheMode':'selected_cached_recording','selectedCache':item,
        'generationElapsedSeconds':record.get('generationElapsedSeconds',record.get('elapsedSeconds')),
        'elapsedSeconds':round(time.monotonic()-started,3),
        'cachedVoice':'当前音色' if signature and record.get('voiceSignature')==signature else '以前保存的音色','sentToQQ':False}
