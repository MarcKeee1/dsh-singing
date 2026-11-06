"""Choose the base octave; phrase_register protects already-high phrases."""
import argparse,json,math,pathlib,sys
import numpy as np
VERSION=2

def choose_register(source_f0,reference_f0):
    source=np.asarray(source_f0);reference=np.asarray(reference_f0)
    source=source[np.isfinite(source)&(source>=65)&(source<=1100)]
    reference=reference[np.isfinite(reference)&(reference>=65)&(reference<=1100)]
    result={'version':VERSION,'semitones':0,'reason':'keep_original_register'}
    if len(source)<200 or len(reference)<200:return {**result,'reason':'insufficient_voiced_pitch'}
    original=float(np.median(source));target=float(np.median(reference));gap=12*math.log2(target/original)
    low_fraction=float(np.mean(source<target/1.35))
    low_register_fraction=float(np.mean(source<180))
    upper_pitch=float(np.percentile(source,90))
    result.update(sourceMedianHz=round(original,2),referenceMedianHz=round(target,2),lowVoiceFraction=round(low_fraction,3),
                  lowRegisterFraction=round(low_register_fraction,3),sourceP90Hz=round(upper_pitch,2),referenceGapSemitones=round(gap,2))
    # Choose only 0 or +12 for the base register. The separate phrase pass
    # can retain already-high phrases; accompaniment and timing stay fixed.
    if gap>=8 and low_fraction>=.65 and abs(gap)-abs(gap-12)>=4:
        result.update(semitones=12,reason='low_source_register_relative_to_reference')
    elif target>=175 and gap>=3 and original<=170 and low_register_fraction>=.65 and upper_pitch<=260:
        # A relaxed speaking sample can sit far below this voice's singing
        # register. Do not let a lower speech median disable low-vocal lifts.
        # Require predominantly low notes and guard against lifting a mixed
        # high/low performance wholesale. No gender/artist label is used.
        result.update(semitones=12,reason='predominantly_low_singing_register')
    return result

def analyze(source,reference):
    from pitch_features import extract,register_sample
    source_f0,source_samples=extract(source)
    reference_f0,reference_samples=extract(reference)
    return choose_register(register_sample(source_f0,source_samples),register_sample(reference_f0,reference_samples))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--reference',required=True);parser.add_argument('--out',required=True);args=parser.parse_args()
    value=analyze(args.source,args.reference);pathlib.Path(args.out).write_text(json.dumps(value,indent=2));print(json.dumps(value))
