"""Isolated UVR karaoke pass: discard harmony, keep the lead for mono-F0 VC."""
import argparse, hashlib, json, os, pathlib, time
from runtime import MODELS,FFMPEG
os.environ['PATH']=str(pathlib.Path(FFMPEG).parent)+os.pathsep+os.environ.get('PATH','')
import numpy as np
import soundfile as sf
import torch
from audio_separator.separator import Separator

def main(source, output):
    start=time.monotonic(); output=pathlib.Path(output); output.mkdir(parents=True,exist_ok=True)
    models=MODELS/'lead-vocal'
    model=models/'UVR_MDXNET_KARA_2.onnx'
    digest=hashlib.sha256(model.read_bytes()).hexdigest()
    assert digest=='bf32e15105a09c0f7dddd2b67346146334d6f3ecb399ed7638eba2ab07cbf5f4'
    torch.set_num_threads(4)
    sep=Separator(model_file_dir=str(models),output_dir=str(output),output_format='WAV',
                  output_single_stem='Vocals',use_soundfile=True,normalization_threshold=1.0,
                  mdx_params={'hop_length':1024,'segment_size':256,'overlap':.5,'batch_size':1,'enable_denoise':True})
    # Pinned KARA2 metadata: avoid mutable model lists and runtime downloads.
    sep.download_model_files=lambda name:(model.name,'MDX','UVR MDXNET Karaoke 2',str(model),None)
    sep.load_model_data_using_hash=lambda path:{'compensate': 1.065, 'mdx_dim_f_set': 2048, 'mdx_dim_t_set': 8, 'mdx_n_fft_scale_set': 5120, 'primary_stem': 'Instrumental', 'is_karaoke': True}
    sep.load_model(model.name)
    assert sep.model_instance.is_karaoke and sep.model_instance.secondary_stem_name=='Vocals'
    # 0.30.2's soundfile writer loses output_dir and can flatten stereo as int16.
    # Keep float channel layout and write a bounded PCM file in our job directory.
    def write_audio(stem_path, samples):
        destination=output/pathlib.Path(stem_path).name
        samples=np.asarray(samples)
        if samples.ndim!=2 or samples.shape[1]!=2 or not np.isfinite(samples).all():
            raise ValueError('Invalid separator channel layout')
        sf.write(destination,samples,44100,subtype='PCM_24')
    sep.model_instance.write_audio=write_audio
    files=sep.separate(str(source),custom_output_names={'Vocals':'lead'})
    lead=output/'lead.wav'; assert lead.is_file(),files
    raw,sr=sf.read(source,always_2d=True); data,rate=sf.read(lead,always_2d=True)
    assert sr==rate and abs(len(raw)-len(data))<=1 and np.isfinite(data).all()
    ratio=float(np.sqrt(np.mean(data**2))/max(1e-9,np.sqrt(np.mean(raw**2))))
    if not .12<ratio<1.6:raise ValueError('Lead extraction removed too much vocal or amplified unexpectedly')
    info={'version':1,'model':model.name,'modelSha256':digest,'sourceSha256':hashlib.sha256(pathlib.Path(source).read_bytes()).hexdigest(),
          'leadSha256':hashlib.sha256(lead.read_bytes()).hexdigest(),'rmsRatio':ratio,'seconds':len(data)/rate,
          'elapsedSeconds':round(time.monotonic()-start,2),'discardOriginalHarmony':True}
    (output/'lead.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    print(json.dumps(info),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args();main(a.source,a.output)
