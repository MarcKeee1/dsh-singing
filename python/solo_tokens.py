"""Private CPU-only CTC anchors. No lyric text is printed or returned."""
import argparse,json,pathlib,subprocess,time
import numpy as np
import sherpa_onnx

def main():
    p=argparse.ArgumentParser();p.add_argument('--audio',required=True);p.add_argument('--output',required=True);p.add_argument('--blocks',required=True);p.add_argument('--model-dir',required=True);p.add_argument('--ffmpeg',required=True);args=p.parse_args()
    blocks=json.loads(args.blocks)
    if not isinstance(blocks,list) or len(blocks)>12 or any(type(b)!=int or b<0 for b in blocks):raise ValueError('Invalid anchor blocks')
    root=pathlib.Path(args.model_dir);started=time.monotonic()
    recognizer=sherpa_onnx.OfflineRecognizer.from_sense_voice(model=str(root/'model.int8.onnx'),tokens=str(root/'tokens.txt'),num_threads=2,provider='cpu',language='auto',use_itn=True)
    rows=[]
    for block in blocks:
        begin=block*20
        done=subprocess.run([args.ffmpeg,'-nostdin','-v','error','-ss',str(begin),'-i',args.audio,'-t','20','-ar','16000','-ac','1','-f','f32le','pipe:1'],capture_output=True,check=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        samples=np.frombuffer(done.stdout,dtype='<f4')
        if not len(samples) or not np.isfinite(samples).all():continue
        stream=recognizer.create_stream();stream.accept_waveform(16000,samples);recognizer.decode_stream(stream);result=stream.result
        anchors=[round(begin+float(t),3) for token,t in zip(result.tokens,result.timestamps) if any(c.isalnum() for c in token) and 0<=float(t)<len(samples)/16000]
        lang=str(result.lang).removeprefix('<|').removesuffix('|>');seconds=len(samples)/16000
        usable=lang in {'zh','en','ja','ko','yue'} and len(anchors)>=max(6,seconds*.3) and anchors[-1]-anchors[0]>=min(5,seconds*.45)
        rows.append({'index':block,'begin':begin,'end':begin+seconds,'language':lang,'anchors':anchors,'usable':usable})
    output=pathlib.Path(args.output);temp=output.with_suffix('.tmp');temp.write_text(json.dumps({'version':1,'blocks':rows,'elapsedSeconds':round(time.monotonic()-started,3)}),encoding='utf-8');temp.replace(output)
    print(json.dumps({'ok':True,'blocks':len(rows)}))

if __name__=='__main__':main()
