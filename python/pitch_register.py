"""Choose one consistent octave from voiced pitch, preserving key and intervals."""
import argparse,json,math,pathlib,sys
import numpy as np
VERSION=1

def choose_register(source_f0,reference_f0):
    source=np.asarray(source_f0);reference=np.asarray(reference_f0)
    source=source[np.isfinite(source)&(source>=65)&(source<=1100)]
    reference=reference[np.isfinite(reference)&(reference>=65)&(reference<=1100)]
    result={'version':VERSION,'semitones':0,'reason':'keep_original_register'}
    if len(source)<200 or len(reference)<200:return {**result,'reason':'insufficient_voiced_pitch'}
    original=float(np.median(source));target=float(np.median(reference));gap=12*math.log2(target/original)
    low_fraction=float(np.mean(source<target/1.35))
    result.update(sourceMedianHz=round(original,2),referenceMedianHz=round(target,2),lowVoiceFraction=round(low_fraction,3))
    # Only lift by a full octave, consistently for the entire song. Do not
    # retune individual notes or move the accompaniment into a different key.
    if gap>=8 and low_fraction>=.65 and abs(gap)-abs(gap-12)>=4:
        result.update(semitones=12,reason='low_source_register_relative_to_reference')
    return result

def analyze(source,reference):
    import librosa,torch
    from runtime import MODELS,VENDOR
    sys.path.insert(0,str(VENDOR));from modules.rmvpe import RMVPE
    torch.set_num_threads(4);model=RMVPE(str(MODELS/'lj1995--VoiceConversionWebUI/rmvpe.pt'),is_half=False,device='cpu')
    def extract(path):
        wave,_=librosa.load(path,sr=16000);span=20*16000
        starts=sorted(set([0,max(0,len(wave)//2-span//2),max(0,len(wave)-span)])) if len(wave)>span else [0]
        return np.concatenate([model.infer_from_audio(wave[start:start+span],thred=.05) for start in starts])
    return choose_register(extract(source),extract(reference))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--reference',required=True);parser.add_argument('--out',required=True);args=parser.parse_args()
    value=analyze(args.source,args.reference);pathlib.Path(args.out).write_text(json.dumps(value,indent=2));print(json.dumps(value))
