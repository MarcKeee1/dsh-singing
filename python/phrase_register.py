"""Keep already-high phrases from receiving an extra octave in a low song."""
import numpy as np

VERSION=1

def plan(source_f0,reference_f0,base_shift):
    if base_shift not in (0,12):raise ValueError('Unsupported base register')
    source=np.asarray(source_f0,dtype=float);reference=np.asarray(reference_f0,dtype=float)
    if source.ndim!=1 or reference.ndim!=1 or not np.isfinite(source).all() or not np.isfinite(reference).all():raise ValueError('Invalid pitch features')
    ref=reference[(reference>=65)&(reference<=1100)]
    result={'version':VERSION,'baseShiftSemitones':base_shift,'intervals':[],'frameRate':100}
    if base_shift==0 or len(ref)<200:return result
    ceiling=float(np.clip(np.median(ref)*1.9,420,480));result['upperRegisterHz']=round(ceiling,2)
    # Hysteresis prevents repeatedly changing octaves on vibrato. A brief
    # unvoiced gap can bridge a phrase; a genuinely lower note cannot.
    active=False;start=0;last=0;voiced=0;runs=[]
    def finish(end):
        if voiced>=12:runs.append({'startFrame':start,'endFrame':end,'semitones':0})
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
    result['intervals']=runs
    return result

def apply(source_f0,profile,base_shift):
    source=np.asarray(source_f0,dtype=float)
    if source.ndim!=1 or not np.isfinite(source).all():raise ValueError('Invalid source pitch')
    if base_shift not in (0,12):raise ValueError('Unsupported base register')
    expected=source*2**(base_shift/12)
    if profile is None:return expected
    if profile.get('version')!=VERSION or profile.get('frameRate')!=100 or profile.get('baseShiftSemitones')!=base_shift:raise ValueError('Invalid phrase register profile')
    previous=0
    for item in profile['intervals']:
        a,b,shift=item['startFrame'],item['endFrame'],item['semitones']
        if isinstance(a,bool) or isinstance(b,bool) or not isinstance(a,int) or not isinstance(b,int) or not previous<=a<b<=len(source) or shift!=0 or base_shift!=12:raise ValueError('Invalid phrase interval')
        expected[a:b]=source[a:b];previous=b
    return expected

def analyze(source,reference,base_shift):
    from pitch_features import extract
    s,_=extract(source);r,_=extract(reference)
    return plan(s,r,base_shift)

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
