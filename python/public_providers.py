"""Ordinary public playback metadata. No cookies, entitlement changes or retry bypasses."""
import html,json,re,urllib.parse,urllib.request
from song_identity import name_key,artist_key

HEADERS={'User-Agent':'Mozilla/5.0'}

def read(url,body=None):
    request=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,
        headers={**HEADERS,**({'Content-Type':'application/json'} if body is not None else {})})
    with urllib.request.urlopen(request,timeout=20) as response:
        data=response.read(4*1024*1024+1)
        if len(data)>4*1024*1024:raise ValueError('平台资料过大')
        return data.decode('utf-8')

def api(url,body=None):return json.loads(read(url,body))

def qq_api(module,method,param):
    result=api('https://u.y.qq.com/cgi-bin/musicu.fcg',{'comm':{'ct':24,'cv':0,'format':'json','uin':0},'req':{'module':module,'method':method,'param':param}})
    item=result.get('req') or {}
    if result.get('code',0)!=0 or item.get('code')!=0:raise ValueError('QQ音乐公开接口暂不可用')
    return item['data']

def resolve_qqmusic(song,artist,source_url=''):
    if source_url:
        p=urllib.parse.urlparse(source_url)
        match=re.fullmatch('/n/ryqq/songDetail/([A-Za-z0-9]+)',p.path)
        if p.scheme!='https' or p.hostname!='y.qq.com' or p.username or p.password or not match:raise ValueError('请提供 QQ音乐单曲详情链接')
        tracks=[qq_api('music.pf_song_detail_svr','get_song_detail_yqq',{'song_mid':match[1],'song_type':0})['track_info']]
    else:
        data=qq_api('music.search.SearchCgiService','DoSearchForQQMusicDesktop',{'query':f'{artist} {song}','search_type':0,'num_per_page':20,'page_num':1})
        tracks=(data.get('body',{}).get('song',{}).get('list') or [])
    for track in tracks:
        if not source_url and (name_key(track.get('title',''))!=name_key(song) or (artist and not any(artist_key(x.get('name',''))==artist_key(artist) for x in track.get('singer',[])))):continue
        # Only anonymous full playback. A preview/premium flag is not an invitation to try other formats.
        if any((track.get('pay') or {}).get(k) for k in ('pay_play','pay_month','pay_status')):continue
        mid=track.get('mid');media=(track.get('file') or {}).get('media_mid')
        if not mid or not media:continue
        data=qq_api('vkey.GetVkeyServer','CgiGetVkey',{'guid':'10000','songmid':[mid],'songtype':[0],'uin':'0','loginflag':0,'platform':'20','filename':['M500'+media+'.mp3']})
        row=next((r for r in data.get('midurlinfo',[]) if r.get('songmid')==mid and r.get('purl')),None)
        if not row:continue
        if row.get('is_preview') or row.get('freeTrialInfo'):continue
        return {'url':urllib.parse.urljoin('https://dl.stream.qqmusic.qq.com/',row['purl']),
            'total':float(track['interval']),'songId':'qq:'+mid,'sourcePage':'https://y.qq.com/n/ryqq/songDetail/'+mid,
            'song':track.get('title',song),'artist':artist or ' / '.join(x.get('name','') for x in track.get('singer',[])),
            'sourceProvider':'qqmusic','referer':'https://y.qq.com/','domains':['.qqmusic.qq.com']}
    raise ValueError('QQ音乐没有返回版本相符、可公开完整播放的音轨')
"""Ordinary public playback metadata. No cookies, entitlement changes or retry bypasses."""
import html,json,re,urllib.parse,urllib.request
from song_identity import name_key,artist_key

HEADERS={'User-Agent':'Mozilla/5.0'}

def read(url,body=None):
    request=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,
        headers={**HEADERS,**({'Content-Type':'application/json'} if body is not None else {})})
    with urllib.request.urlopen(request,timeout=20) as response:
        data=response.read(4*1024*1024+1)
        if len(data)>4*1024*1024:raise ValueError('平台资料过大')
        return data.decode('utf-8')

def api(url,body=None):return json.loads(read(url,body))

def qq_api(module,method,param):
    result=api('https://u.y.qq.com/cgi-bin/musicu.fcg',{'comm':{'ct':24,'cv':0,'format':'json','uin':0},'req':{'module':module,'method':method,'param':param}})
    item=result.get('req') or {}
    if result.get('code',0)!=0 or item.get('code')!=0:raise ValueError('QQ音乐公开接口暂不可用')
    return item['data']

def resolve_qqmusic(song,artist,source_url=''):
    if source_url:
        p=urllib.parse.urlparse(source_url)
        match=re.fullmatch('/n/ryqq/songDetail/([A-Za-z0-9]+)',p.path)
        if p.scheme!='https' or p.hostname!='y.qq.com' or p.username or p.password or not match:raise ValueError('请提供 QQ音乐单曲详情链接')
        tracks=[qq_api('music.pf_song_detail_svr','get_song_detail_yqq',{'song_mid':match[1],'song_type':0})['track_info']]
    else:
        data=qq_api('music.search.SearchCgiService','DoSearchForQQMusicDesktop',{'query':f'{artist} {song}','search_type':0,'num_per_page':20,'page_num':1})
        tracks=(data.get('body',{}).get('song',{}).get('list') or [])
    for track in tracks:
        if name_key(track.get('title',''))!=name_key(song) or not any(artist_key(x.get('name',''))==artist_key(artist) for x in track.get('singer',[])):continue
        # Only anonymous full playback. A preview/premium flag is not an invitation to try other formats.
        if any((track.get('pay') or {}).get(k) for k in ('pay_play','pay_month','pay_status')):continue
        mid=track.get('mid');media=(track.get('file') or {}).get('media_mid')
        if not mid or not media:continue
        data=qq_api('vkey.GetVkeyServer','CgiGetVkey',{'guid':'10000','songmid':[mid],'songtype':[0],'uin':'0','loginflag':0,'platform':'20','filename':['M500'+media+'.mp3']})
        row=next((r for r in data.get('midurlinfo',[]) if r.get('songmid')==mid and r.get('purl')),None)
        if not row:continue
        if row.get('is_preview') or row.get('freeTrialInfo'):continue
        return {'url':urllib.parse.urljoin('https://dl.stream.qqmusic.qq.com/',row['purl']),
            'total':float(track['interval']),'songId':'qq:'+mid,'sourcePage':'https://y.qq.com/n/ryqq/songDetail/'+mid,
            'sourceProvider':'qqmusic','referer':'https://y.qq.com/','domains':['.qqmusic.qq.com']}
    raise ValueError('QQ音乐没有返回版本相符、可公开完整播放的音轨')
