"""Source-bound automatic solo masks; no song names or hand-written cut points."""
import hashlib,json,pathlib,subprocess,time,uuid,sys
import numpy as np
import soundfile as sf

VERSION=1
FRAME_RATE=100

def digest(path):
    sha=hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):sha.update(data)
    return sha.hexdigest()

def save(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:temp.write_text(json.dumps(value),encoding='utf-8');temp.replace(path)
    finally:temp.unlink(missing_ok=True)

def runs(active):
    changes=np.diff(np.r_[False,np.asarray(active,dtype=bool),False].astype(np.int8))
    return list(zip(np.where(changes==1)[0].tolist(),np.where(changes==-1)[0].tolist()))

def frame_rms(wave,rate,count):
    wave=np.asarray(wave)
    if wave.ndim==1:wave=wave[:,None]
    hop=rate//FRAME_RATE;n=min(count,len(wave)//hop)
    return np.sqrt(np.mean(wave[:n*hop].reshape(n,hop,-1).astype('float64')**2,axis=(1,2)))

def acoustic_candidates(f0,rms):
    f0=np.asarray(f0,dtype=float);rms=np.asarray(rms,dtype=float)
    if f0.ndim!=1 or rms.ndim!=1 or not np.isfinite(f0).all() or not np.isfinite(rms).all():raise ValueError('Invalid solo features')
    n=min(len(f0),len(rms));f0=f0[:n];rms=rms[:n];valid=(f0>=65)&(f0<=1100)
    # Tiny tracking dropouts are vibrato/noise, not a new syllable.
    for a,b in runs(~valid):
        if 0<a<b<n and b-a<=3:valid[a:b]=True
    voiced=runs(valid);items=[]
    for (pa,pb),(a,b) in zip(voiced,voiced[1:]):
        gap=(a-pb)/FRAME_RATE
        if not .06<=gap<=.32 or pb-pa<35:continue
        prior=f0[max(pa,pb-50):pb];prior=prior[prior>=65]
        if len(prior)<25:continue
        pitch=float(np.median(prior));prior_cents=1200*np.log2(prior/pitch)
        if np.percentile(np.abs(prior_cents),90)>100:continue
        prefix=f0[a:b];different=(prefix<65)|(np.abs(1200*np.log2(np.maximum(prefix,1)/pitch))>160)
        stop=b
        for x,y in runs(different):
            if y-x>=5:stop=a+x;break
        if not .18<=(stop-a)/FRAME_RATE<=1.4:continue
        notes=f0[a:stop];notes=notes[notes>=65]
        if len(notes)<15 or np.mean(np.abs(1200*np.log2(notes/pitch))<=120)<.9:continue
        energy=float(np.percentile(rms[a:stop],75)/max(1e-9,np.percentile(rms[max(pa,pb-90):pb],75)))
        if not .08<=energy<=.9:continue
        items.append({'start':a/FRAME_RATE,'end':stop/FRAME_RATE,'previousEnd':pb/FRAME_RATE,'gapSeconds':gap,'pitchDifferenceCents':round(float(1200*np.log2(np.median(notes)/pitch)),2),'energyRatio':round(energy,3)})
    return items

def choose_echoes(candidates,blocks,total):
    edits=[];unresolved=[]
    for candidate in candidates:
        a,b=candidate['start'],candidate['end'];decision=None
        for block in blocks:
            if not block.get('usable') or not block['begin']+.15<a<b<block['end']-.15:continue
            anchors=np.asarray(block['anchors'],dtype=float)
            if len(anchors)<6 or not np.isfinite(anchors).all() or np.any(np.diff(anchors)<0):continue
            before=anchors[anchors<a-.10];after=anchors[anchors>=b-.03]
            if not len(before) or not len(after):continue
            previous=float(before[-1]);following=float(after[0])
            # An independently recognized word always wins over an acoustic
            # echo guess; missing/poor anchors never authorize deletion.
            if np.any((anchors>=a-.10)&(anchors<b-.03)):continue
            if following-previous<1.6 or a-previous<.65 or candidate['previousEnd']-previous<.35 or not -.03<=following-b<=.45:continue
            start=max(previous+.20,candidate['previousEnd']-.10)
            end=min(following,b+.18,total)
            if .18<=end-start<=1.65:
                decision={'start':round(start,3),'end':round(end,3),'kind':'unanchored_same_note_reentry','confidence':'high','evidence':{**candidate,'precedingAnchor':previous,'followingAnchor':following}};break
        if decision:edits.append(decision)
        else:unresolved.append(candidate)
    edits.sort(key=lambda x:x['start'])
    if sum(x['end']-x['start'] for x in edits)>min(25,total*.08) or any(b['start']<a['end'] for a,b in zip(edits,edits[1:])):
        return [],candidates
    return edits,unresolved

def quiet_ranges(rms):
    rms=np.asarray(rms);threshold=max(.00003,min(.0005,float(np.percentile(rms,95))*.01)) if len(rms) else .00003
    return [{'start':round((a+12)/100,3),'end':round((b-12)/100,3),'kind':'source_silence','confidence':'high'} for a,b in runs(rms<threshold) if b-a>=38]

def lexical_hint_supported(job):
    path=pathlib.Path(job)/'source-info.json'
    if not path.is_file():return True
    try:
        value=json.loads(path.read_text(encoding='utf-8'));text=str(value.get('song',''))+' '+str(value.get('artist',''))
        return not any('\u0400'<=c<='\u052f' or '\u0600'<=c<='\u06ff' or '\u0900'<=c<='\u097f' or '\u0e00'<=c<='\u0e7f' for c in text)
    except (OSError,ValueError,TypeError):return False

def prepare(job,root,code_dir=None,*,anchors_provider=None,pitch_provider=None):
    job=pathlib.Path(job).resolve();root=pathlib.Path(root).resolve();code_dir=pathlib.Path(code_dir or __file__).resolve()
    if code_dir.is_file():code_dir=code_dir.parent
    if job.parent!=root/'jobs':raise ValueError('Solo job is outside the jobs directory')
    from runtime import CONFIG,MODELS,FFMPEG
    if not CONFIG.get('autoSoloGuard',True):return {'version':VERSION,'status':'disabled','mainPreserved':True}
    started=time.monotonic();lead=job/'lead/lead.wav';source=job/'source.wav'
    source_sha,lead_sha=digest(source),digest(lead)
    model=MODELS/'sensevoice/model.int8.onnx';tokens=model.with_name('tokens.txt')
    model_id=digest(model)+digest(tokens) if model.is_file() and tokens.is_file() else 'unavailable'
    identity=[VERSION,source_sha,lead_sha,digest(__file__),digest(code_dir/'solo_tokens.py'),model_id]
    cache=root/'edited-performance-cache/solo-plans'/(hashlib.sha256(json.dumps(identity).encode()).hexdigest()+'.json')
    if anchors_provider is None and pitch_provider is None and cache.is_file():
        try:
            plan=json.loads(cache.read_text(encoding='utf-8'))
            if plan.get('identity')==identity and valid_plan(plan,source_sha,lead_sha):save(job/'solo-plan.json',plan);return summary(plan,True,time.monotonic()-started)
        except (OSError,ValueError,TypeError):pass
    wave,rate=sf.read(lead,always_2d=True);total=len(wave)/rate
    if pitch_provider is None:
        from pitch_features import extract
        pitch_provider=lambda p:extract(p)[0]
    f0=pitch_provider(lead);rms=frame_rms(wave,rate,len(f0));f0=f0[:len(rms)]
    candidates=acoustic_candidates(f0,rms);blocks=[];asr_state='not_needed';errors=[]
    if candidates and lexical_hint_supported(job):
        indices=sorted(set(int(c['start']//20) for c in candidates))[:12]
        try:
            if anchors_provider is not None:blocks=anchors_provider(lead,indices)
            elif model_id!='unavailable':
                output=job/'solo-anchors.json'
                done=subprocess.run([str(CONFIG.get('soloPython') or sys.executable),str(code_dir/'solo_tokens.py'),'--audio',str(lead),'--output',str(output),'--blocks',json.dumps(indices),'--model-dir',str(model.parent),'--ffmpeg',FFMPEG],capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env={**__import__('os').environ,'PYTHONIOENCODING':'utf-8'})
                if done.returncode:raise ValueError('anchor_worker_failed')
                if output.stat().st_size>512*1024:raise ValueError('anchors_too_large')
                blocks=json.loads(output.read_text(encoding='utf-8'))['blocks']
            asr_state='usable' if any(b.get('usable') for b in blocks) else 'unavailable_or_uncertain'
        except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as error:errors.append(type(error).__name__);asr_state='unavailable_or_uncertain'
    elif candidates:asr_state='language_not_supported'
    echoes,uncertain=choose_echoes(candidates,blocks,total)
    plan={'version':VERSION,'identity':identity,'sourceSha256':source_sha,'leadSha256':lead_sha,'seconds':total,'frameRate':100,'fadeSeconds':.055,
          'ranges':quiet_ranges(rms)+echoes,'echoes':echoes,'uncertainCount':len(uncertain),'asrStatus':asr_state,'errors':errors,'candidateCount':len(candidates),'recognitionBlocks':len(blocks),'lyricsStored':False}
    if not valid_plan(plan,source_sha,lead_sha):raise ValueError('Invalid automatic solo plan')
    save(job/'solo-plan.json',plan)
    if not errors:save(cache,plan)
    return summary(plan,False,time.monotonic()-started)

def valid_plan(plan,source_sha,lead_sha):
    try:
        if plan['version']!=VERSION or plan['sourceSha256']!=source_sha or plan['leadSha256']!=lead_sha or not np.isfinite(plan['seconds']) or plan['seconds']<=0 or len(plan['ranges'])>5000:return False
        return all(x['kind'] in {'source_silence','unanchored_same_note_reentry'} and x['confidence']=='high' and 0<=x['start']<x['end']<=plan['seconds']+.001 for x in plan['ranges'])
    except (KeyError,TypeError,ValueError):return False

def summary(plan,cache_hit,elapsed):
    return {'version':VERSION,'status':'ready','sourceBound':True,'automatic':True,'echoCorrections':len(plan['echoes']),'silenceGuards':sum(x['kind']=='source_silence' for x in plan['ranges']),'uncertainCandidatesPreserved':plan['uncertainCount'],'asrStatus':plan['asrStatus'],'recognitionBlocks':plan['recognitionBlocks'],'cacheHit':cache_hit,'elapsedSeconds':round(elapsed,3),'paidApiCalls':0,'extraGpuPasses':0}

def apply(voice,rate,job):
    from runtime import CONFIG
    if not CONFIG.get('autoSoloGuard',True):return voice,None
    job=pathlib.Path(job);path=job/'solo-plan.json'
    if not path.is_file():return voice,None
    if path.is_symlink() or path.stat().st_size>1024*1024:raise ValueError('Invalid solo plan file')
    plan=json.loads(path.read_text(encoding='utf-8'))
    if not valid_plan(plan,digest(job/'source.wav'),digest(job/'lead/lead.wav')):raise ValueError('Solo plan does not match this recording')
    if abs(len(voice)/rate-plan['seconds'])>.1:raise ValueError('Solo mask has a different timeline')
    from vocal_edits import rule
    if rule(job.parent.parent,plan['sourceSha256']):return voice,{'version':VERSION,'manualOverride':True,'automaticRangesApplied':0}
    envelope=np.ones(len(voice));fade=round(rate*.055)
    for item in plan['ranges']:
        a=max(0,round(item['start']*rate));b=min(len(voice),round(item['end']*rate));n=min(fade,(b-a)//2)
        gain=np.zeros(max(0,b-a))
        if n:gain[:n]=(1+np.cos(np.linspace(0,np.pi,n)))/2;gain[-n:]=gain[:n][::-1]
        envelope[a:b]=np.minimum(envelope[a:b],gain)
    result=np.asarray(voice)*envelope.reshape((-1,)+(1,)*(np.asarray(voice).ndim-1))
    return result,{'version':VERSION,'automaticRangesApplied':len(plan['ranges']),'echoCorrections':len(plan['echoes']),'planSha256':digest(path),'sourceBound':True}
