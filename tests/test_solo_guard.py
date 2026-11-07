import pathlib,sys,tempfile,json,unittest,hashlib
from unittest.mock import patch
import numpy as np,soundfile as sf
HERE=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent/'python'))
import solo_guard as guard

def features(offset=0):
    f=np.zeros(3000);r=np.full(3000,.005)
    for a,b,hz,gain in [(1+offset,3.69+offset,465,.2),(3.8+offset,4.75+offset,465,.13),(4.75+offset,5.2+offset,300,.17)]:
        f[round(a*100):round(b*100)]=hz;r[round(a*100):round(b*100)]=gain
    return f,r

def block(offset=0):return {'begin':0,'end':30,'usable':True,'language':'zh','anchors':[1.2+offset,1.5+offset,1.8+offset,2.1+offset,2.2+offset,4.86+offset,5.1+offset]}

class SoloTests(unittest.TestCase):
    def test_same_note_unanchored_reentry_is_detected_at_any_position(self):
        for offset in [0,8,12]:
            f,r=features(offset);c=guard.acoustic_candidates(f,r);edits,unknown=guard.choose_echoes(c,[block(offset)],30)
            self.assertEqual(len(edits),1);self.assertAlmostEqual(edits[0]['start'],3.59+offset);self.assertAlmostEqual(edits[0]['end'],4.86+offset)
    def test_recognized_repeated_word_is_protected(self):
        f,r=features();b=block();b['anchors'].insert(-2,4.1);b['anchors'].sort()
        self.assertEqual(guard.choose_echoes(guard.acoustic_candidates(f,r),[b],30)[0],[])
    def test_missing_or_unusable_asr_never_authorizes_an_echo_cut(self):
        f,r=features();c=guard.acoustic_candidates(f,r)
        for blocks in [[],[{**block(),'usable':False}],[{**block(),'anchors':[]}]]:self.assertEqual(guard.choose_echoes(c,blocks,30)[0],[])
    def test_continuous_held_note_is_not_an_echo(self):
        f,r=features();f[369:380]=465
        self.assertEqual(guard.acoustic_candidates(f,r),[])
    def test_brief_pitch_tracker_dropout_is_not_a_new_syllable(self):
        f=np.full(1000,465.);f[500:503]=0
        self.assertEqual(guard.acoustic_candidates(f,np.full(1000,.2)),[])
    def test_different_note_or_louder_new_phrase_is_preserved(self):
        for kind in ['pitch','energy']:
            f,r=features()
            if kind=='pitch':f[380:475]=350
            else:r[380:475]=.24
            self.assertEqual(guard.acoustic_candidates(f,r),[])
    def test_dense_words_short_anchor_gap_and_chunk_boundaries_are_protected(self):
        f,r=features();c=guard.acoustic_candidates(f,r)
        for b in [{**block(),'anchors':[.1,.2,.3,.4,3.4,4.86,5.1]},{**block(),'begin':3.7},{**block(),'end':4.8}]:self.assertEqual(guard.choose_echoes(c,[b],30)[0],[])
    def test_excessive_removal_budget_is_rejected(self):
        f,r=features();self.assertEqual(guard.choose_echoes(guard.acoustic_candidates(f,r),[block()],8)[0],[])
    def test_breaths_and_short_gaps_remain_while_real_source_silence_is_guarded(self):
        r=np.ones(500)*.1;r[0:50]=0;r[100:120]=0;r[200:260]=.001
        plan=guard.quiet_ranges(r);self.assertEqual(len(plan),1);self.assertEqual(plan[0]['start'],.12);self.assertEqual(plan[0]['end'],.38)
    def fixture(self,root):
        job=root/'jobs/fixture';(job/'lead').mkdir(parents=True);f,r=features();rate=1000
        wave=np.repeat(r,10)[:,None];sf.write(job/'source.wav',wave,rate,subtype='FLOAT');sf.write(job/'lead/lead.wav',wave,rate,subtype='FLOAT')
        return job,f,wave,rate
    def test_plan_applies_after_conversion_without_changing_timing_pitch_or_music(self):
        with tempfile.TemporaryDirectory(prefix='solo-guard-') as t:
            root=pathlib.Path(t);job,f,wave,rate=self.fixture(root)
            result=guard.prepare(job,root,HERE.parent/'python',pitch_provider=lambda _:f,anchors_provider=lambda *_:[block()]);before=wave.copy();clean,settings=guard.apply(wave,rate,job)
            self.assertEqual(result['echoCorrections'],1);self.assertEqual(clean.shape,wave.shape);np.testing.assert_array_equal(wave,before)
            self.assertEqual(float(np.max(np.abs(clean[3700:4800]))),0);np.testing.assert_array_equal(clean[5000:],wave[5000:]);self.assertTrue(settings['sourceBound'])
    def test_manual_accepted_correction_takes_priority(self):
        with tempfile.TemporaryDirectory(prefix='solo-guard-') as t:
            root=pathlib.Path(t);job,f,wave,rate=self.fixture(root)
            guard.prepare(job,root,HERE.parent/'python',pitch_provider=lambda _:f,anchors_provider=lambda *_:[block()]);sha=guard.digest(job/'source.wav');folder=root/'edited-performance-cache/vocal-edits';folder.mkdir();(folder/(sha+'.json')).write_text(json.dumps({'version':1,'sourceSha256':sha,'muteIntervals':[[3.58,4.86]]}))
            clean,settings=guard.apply(wave,rate,job);np.testing.assert_array_equal(clean,wave);self.assertTrue(settings['manualOverride'])
    def test_disabled_setting_skips_analysis_and_ignores_an_existing_plan(self):
        import runtime
        with tempfile.TemporaryDirectory(prefix='solo-guard-') as t:
            root=pathlib.Path(t);job,f,wave,rate=self.fixture(root)
            guard.prepare(job,root,HERE.parent/'python',pitch_provider=lambda _:f,anchors_provider=lambda *_:[block()])
            with patch.dict(runtime.CONFIG,{'autoSoloGuard':False}):
                result=guard.prepare(job,root,HERE.parent/'python',pitch_provider=lambda _:self.fail('disabled analysis ran'))
                clean,settings=guard.apply(wave,rate,job)
            self.assertEqual(result['status'],'disabled');self.assertIs(clean,wave);self.assertIsNone(settings)
    def test_source_changes_cannot_reuse_a_plan(self):
        with tempfile.TemporaryDirectory(prefix='solo-guard-') as t:
            root=pathlib.Path(t);job,f,wave,rate=self.fixture(root);guard.prepare(job,root,HERE.parent/'python',pitch_provider=lambda _:f,anchors_provider=lambda *_:[block()]);(job/'source.wav').write_bytes(b'another recording')
            with self.assertRaises(ValueError):guard.apply(wave,rate,job)
    def test_missing_plan_keeps_old_caches_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='solo-guard-') as t:
            wave=np.ones((100,1));clean,settings=guard.apply(wave,1000,pathlib.Path(t));self.assertIs(clean,wave);self.assertIsNone(settings)
    def test_asr_failure_and_unsupported_language_preserve_main(self):
        with tempfile.TemporaryDirectory(prefix='solo-guard-') as t:
            root=pathlib.Path(t);job,f,wave,rate=self.fixture(root)
            with patch.object(guard.subprocess,'run',side_effect=OSError('unavailable')):
                result=guard.prepare(job,root,HERE.parent/'python',pitch_provider=lambda _:f)
            self.assertEqual(result['echoCorrections'],0);self.assertEqual(result['asrStatus'],'unavailable_or_uncertain')
            (job/'source-info.json').write_text('{"song":"Колыбельная"}',encoding='utf-8')
            result=guard.prepare(job,root,HERE.parent/'python',pitch_provider=lambda _:f,anchors_provider=lambda *_:self.fail('unsupported language must not use a five-language model'))
            self.assertEqual(result['asrStatus'],'language_not_supported');self.assertEqual(result['echoCorrections'],0)
    def test_no_acoustic_candidate_needs_no_asr_call(self):
        with tempfile.TemporaryDirectory(prefix='solo-guard-') as t:
            root=pathlib.Path(t);job,f,wave,rate=self.fixture(root);f=np.full_like(f,400)
            result=guard.prepare(job,root,HERE.parent/'python',pitch_provider=lambda _:f,anchors_provider=lambda *_:self.fail('unexpected ASR call'));self.assertEqual(result['recognitionBlocks'],0)
    def test_malformed_features_and_plans_fail_closed(self):
        with self.assertRaises(ValueError):guard.acoustic_candidates(np.array([np.nan]),np.ones(1))
        self.assertFalse(guard.valid_plan({'version':1,'sourceSha256':'x'},'x','y'))

if __name__=='__main__':unittest.main(verbosity=2)
