"""Compare converted singing against source melody without octave folding."""
import argparse
import json
import pathlib
import sys

import librosa
import numpy as np
import soundfile as sf
import torch

from runtime import MODELS, VENDOR
sys.path.insert(0,str(VENDOR))
from modules.rmvpe import RMVPE


def compare_pitch(source, converted, expected_shift=0):
    if expected_shift not in (0,12):raise ValueError('Unsupported expected register shift')
    size = min(len(source), len(converted))
    source, converted = np.asarray(source[:size])*2**(expected_shift/12), np.asarray(converted[:size])
    source_voiced = source > 50
    paired = source_voiced & (converted > 50)
    if paired.sum() < 20:
        return {'passed': False, 'reason': 'not_enough_voiced_frames', 'sourceVoicedFrames': int(source_voiced.sum()), 'convertedVoicedFrames': int((converted > 50).sum())}
    cents = 1200 * np.log2(converted[paired] / source[paired])
    absolute = np.abs(cents)
    coverage = float(paired.sum() / max(1, source_voiced.sum()))
    median = float(np.median(absolute))
    p90 = float(np.percentile(absolute, 90))
    result = {
        'voicedFrames': int(paired.sum()), 'voicedCoverage': round(coverage, 4),
        'medianAbsoluteCents': round(median, 2), 'p90AbsoluteCents': round(p90, 2),
        'meanSignedCents': round(float(np.mean(cents)), 2),
        'withinHalfSemitone': round(float(np.mean(absolute <= 50)), 4),
        'withinOneSemitone': round(float(np.mean(absolute <= 100)), 4),
        'octaveFolding': False,
        'expectedShiftSemitones':expected_shift,
        'passed': median <= 50 and p90 <= 150 and coverage >= 0.75,
        'note': 'Relative to extracted source F0, not a guarantee of perfect notes or timbre quality.',
    }
    return result


def check(source_path, converted_path, expected_shift=0):
    from pitch_features import extract
    source_f0,source_samples=extract(source_path)
    converted_f0,converted_samples=extract(converted_path)
    result = compare_pitch(source_f0, converted_f0,expected_shift)
    result['sourceSeconds'] = round(source_samples / 16000, 4)
    result['convertedSeconds'] = round(converted_samples / 16000, 4)
    result['durationDifferenceMs'] = round(abs(source_samples - converted_samples) / 16, 2)
    if result['durationDifferenceMs'] > 80:
        result['passed'] = False
        result['durationMismatch'] = True
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--converted', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--expected-shift',type=int,choices=[0,12],default=0)
    args = parser.parse_args()
    result = check(args.source, args.converted,args.expected_shift)
    pathlib.Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
