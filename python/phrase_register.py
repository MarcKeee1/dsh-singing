"""Map low and high vocal phrases independently into the reference range."""
import numpy as np

VERSION=2

def plan(source_f0,reference_f0,base_shift,*,enabled=True):
    if base_shift not in (0,12):raise ValueError('Unsupported base register')
    source=np.asarray(source_f0,dtype=float);reference=np.asarray(reference_f0,dtype=float)
    if source.ndim!=1 or reference.ndim!=1 or not np.isfinite(source).all() or not np.isfinite(reference).all():raise ValueError('Invalid pitch features')
    ref=reference[(reference>=65)&(reference<=1100)]
    result={'version':VERSION,'baseShiftSemitones':base_shift,'intervals':[],'frameRate':100}
    if not enabled or len(ref)<200 or (base_shift==0 and int(((source>=65)&(source<=1100)).sum())<200):return result
    ceiling=float(np.clip(np.median(ref)*1.9,420,480));result['upperRegisterHz']=round(ceiling,2)
    shifts=np.full(len(source),base_shift,dtype=np.int8)
    # Speaking pitch is lower than the comfortable singing centre. Judge
    # each breath phrase rather than using only the whole-song median.
    centre=float(np.median(ref)*1.4);result['singingCentreHz']=round(centre,2)
    if base_shift==0 and np.median(ref)>=175:
        indices=np.flatnonzero((source>=65)&(source<=1100))
        phrases=[];a=last=int(indices[0])
        for index in indices[1:]:
            index=int(index)
            if index-last>20 or index-a>=800:phrases.append((a,last+1));a=index
            last=index
        phrases.append((a,last+1))
        for a,b in phrases:
            notes=source[a:b];notes=notes[(notes>=65)&(notes<=1100)]
            if len(notes)<30:continue
            gap=12*np.log2(centre/np.median(notes))
            if abs(gap)-abs(gap-12)>=2:shifts[a:b]=12
    # Hysteresis prevents repeatedly changing octaves on vibrato. A brief
    # unvoiced gap can bridge a phrase; a genuinely lower note cannot.
    active=False;start=0;last=0;voiced=0
    def finish(end):
        if voiced>=12:shifts[start:end]=0
    for i,value in enumerate(source):
        valid=65<=value<=1100
        if not active:
            if valid and value*2>ceiling:active=True;start=i;last=i;voiced=1
        elif valid and value*2>=ceiling*.95:
            last=i;voiced+=1
        elif not valid and i-last<=6:
            continue
        else:
            finish(last+1);active=False
            if valid and value*2>ceiling:active=True;start=i;last=i;voiced=1
    if active:finish(last+1)
    # Very high source frames must never be doubled, even if a polyphonic
    # pitch tracker switches harmonics for less than the phrase duration.
    # Hysteresis above still handles vibrato close to the register boundary.
    shifts[(source>=65)&(source<=1100)&(source*2>ceiling*1.1)]=0
    runs=[];start=0
    while start<len(shifts):
        if shifts[start]==base_shift:start+=1;continue
        end=start+1
        while end<len(shifts) and shifts[end]==shifts[start]:end+=1
        runs.append({'startFrame':start,'endFrame':end,'semitones':int(shifts[start])});start=end
    result['intervals']=runs
    return result

def apply(source_f0,profile,base_shift):
    source=np.asarray(source_f0,dtype=float)
    if source.ndim!=1 or not np.isfinite(source).all():raise ValueError('Invalid source pitch')
    if base_shift not in (0,12):raise ValueError('Unsupported base register')
    expected=source*2**(base_shift/12)
    if profile is None:return expected
    version=profile.get('version')
    if version not in (1,VERSION) or profile.get('frameRate')!=100 or profile.get('baseShiftSemitones')!=base_shift:raise ValueError('Invalid phrase register profile')
    previous=0
    for item in profile['intervals']:
        a,b,shift=item['startFrame'],item['endFrame'],item['semitones']
        if isinstance(a,bool) or isinstance(b,bool) or not isinstance(a,int) or not isinstance(b,int) or not previous<=a<b<=len(source) or shift not in (0,12) or shift==base_shift or (version==1 and (shift!=0 or base_shift!=12)):raise ValueError('Invalid phrase interval')
        expected[a:b]=source[a:b]*2**(shift/12);previous=b
    return expected

def analyze(source,reference,base_shift,*,enabled=True):
    from pitch_features import extract
    s,_=extract(source);r,_=extract(reference)
    return plan(s,r,base_shift,enabled=enabled)

def local_quality(quality):
    """Octave accuracy is local; voiced coverage is enforced on the full track.

    A 0.2-second backing phrase often has fewer than 20 paired frames, so
    report it as unassessed rather than inventing a local accuracy score.
    """
    result=dict(quality)
    if quality.get('voicedFrames',0)<20:
        result.update(assessed=False,passed=None)
    else:
        result.update(assessed=True,pitchOnly=True,coverageCheckedAtTrackLevel=True,
                      passed=quality['medianAbsoluteCents']<=50 and quality['p90AbsoluteCents']<=150)
    return result
