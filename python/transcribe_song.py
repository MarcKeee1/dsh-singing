"""Offline, CPU-only word timestamps for the actual selected source recording."""
import argparse
import json
import pathlib
import os

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--audio',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    import torch
    import soundfile as sf
    from transformers import pipeline
    torch.set_num_threads(4)
    from runtime import MODELS
    model=MODELS/'openai--whisper-small'
    recognizer=pipeline('automatic-speech-recognition',model=str(model),device='cpu',
                        model_kwargs={'attn_implementation':'eager'})
    audio,sample_rate=sf.read(args.audio,dtype='float32')
    result=recognizer({'raw':audio,'sampling_rate':sample_rate},return_timestamps='word',
                     chunk_length_s=30,stride_length_s=(4,2),
                     generate_kwargs={'task':'transcribe','num_beams':1,'do_sample':False})
    # Keep recognition private and on disk; never print lyrics into tool output.
    words=[]
    for chunk in result.get('chunks',[]):
        stamps=chunk.get('timestamp') or []
        if len(stamps)==2 and stamps[0] is not None and stamps[1] is not None:
            words.append({'text':chunk['text'],'start':float(stamps[0]),'end':float(stamps[1])})
    target=pathlib.Path(args.output)
    temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps({'version':1,'words':words},ensure_ascii=False),encoding='utf-8')
    temp.replace(target)
    print(json.dumps({'ok':True,'wordCount':len(words)}))

if __name__=='__main__':main()
