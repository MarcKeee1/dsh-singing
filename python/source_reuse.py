"""Reuse a full original audio file proven by a successful cached performance."""
import pathlib,json,hashlib,urllib.parse
import soundfile as sf
from song_identity import name_key,artist_key

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def find_verified_full(root,song,artist='',source_url=''):
    root=pathlib.Path(root);folder=(root/'song-cache').resolve();choices=[]
    for file in (root/'performance-cache').glob('*.json'):
        try:
            r=json.loads(file.read_text('utf-8'));s=r.get('sourceInfo') or {}
            if not r.get('ok') or not r.get('quality',{}).get('passed') or s.get('sourceProvider')=='local':continue
            if name_key(s.get('song',''))!=name_key(song) or not s.get('artist') or not s.get('songId'):continue
            if artist and artist_key(s['artist'])!=artist_key(artist):continue
            if source_url and source_url.rstrip('/')!=str(s.get('sourcePage','')).rstrip('/'):continue
            page=urllib.parse.urlparse(s.get('sourcePage',''))
            if page.scheme!='https' or page.hostname not in {'www.bilibili.com','bilibili.com','music.163.com','y.qq.com'}:continue
            performance=file.with_suffix('.mp3')
            if performance.is_symlink() or digest(performance)!=r.get('audioSha256'):continue
            source=pathlib.Path(s['source']).resolve(strict=True)
            if source.parent!=folder or source.is_symlink() or source.suffix!='.wav':continue
            full=json.loads(source.with_suffix('.json').read_text('utf-8'))
            if full.get('sourceComplete') is not True or full.get('sourceStartSeconds')!=0:continue
            if full.get('songId')!=s['songId'] or full.get('sha256')!=s.get('sha256') or digest(source)!=full['sha256']:continue
            if name_key(full.get('song',''))!=name_key(song) or artist_key(full.get('artist',''))!=artist_key(s['artist']):continue
            seconds=sf.info(source).duration
            if seconds<5 or abs(seconds-float(full['seconds']))>max(2,seconds*.01):continue
            value={**full,'source':str(source),'seconds':seconds,'sourceTotalSeconds':seconds,
                   'sourceReuse':{'kind':'verified_full_original','performanceId':file.stem},
                   'sourceAttempts':[{'provider':s['sourceProvider'],'status':'local_verified_source'}]}
            choices.append((artist_key(s['artist']),file.stat().st_mtime,value))
        except (OSError,ValueError,KeyError,TypeError,RuntimeError):continue
    if not choices or len({x[0] for x in choices})>1:return None
    return max(choices,key=lambda x:x[1])[2]
