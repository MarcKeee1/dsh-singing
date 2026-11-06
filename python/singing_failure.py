"""Public, stage-specific failures without local paths or raw model logs."""
import pathlib,json

class SingingFailure(RuntimeError):
    def __init__(self,stage,code,message):
        super().__init__(message);self.stage=stage;self.code=code

def from_job(job,fallback='local_processing',timeout=False):
    try:
        data=json.loads((pathlib.Path(job)/'stages.json').read_text('utf-8'))
    except (OSError,ValueError):data={}
    stage=data.get('failedStage') or fallback;message=str(data.get('errorMessage',''))
    if not message:
        try:tail=(pathlib.Path(job)/'worker.log').read_text('utf-8',errors='replace')[-8192:]
        except OSError:tail=''
        for signature,known_stage in [('This excerpt contains too little singing','vocalValidation'),('Harmony pitch/timing QA failed','harmonyQuality')]:
            if signature in tail:message=signature;stage=known_stage;break
    if timeout:return SingingFailure(stage,'processing_timeout','本地处理在'+stage+'阶段超时，未发送；不能据此判断歌曲太长或音源不存在')
    if 'too little singing' in message:
        return SingingFailure('vocal_validation','no_usable_vocals','音源已取得，但分离后有效人声太少，可能是伴奏或人声过弱；尚未开始换声，未发送')
    known={
      'separation':('vocal_separation_failed','原曲已取得，人声与伴奏分离失败，未发送'),
      'leadSeparation':('lead_separation_failed','主唱与和声分离失败，未发送'),
      'conversion':('conversion_failed','已取得人声，但本地音色转换失败，未发送'),
      'quality':('pitch_check_failed','歌声音准或时长检查未通过，未发送'),
      'harmonyQuality':('harmony_pitch_failed','和声音准或时长检查未通过，未发送'),
      'audio_decode':('audio_decode_failed','音源读取或解码失败，尚未开始演唱'),
      'audio_encode':('audio_encode_failed','已完成换声，但最终音频编码失败，未发送')}
    code,text=known.get(stage,('local_processing_failed','本地歌声处理失败，当前未取得更具体的阶段信息；不要推测是歌曲太长或下载受限'))
    return SingingFailure(stage,code,text)

def public_details(error):
    return {'failureStage':error.stage,'failureCode':error.code,'note':'只按已确认的阶段解释；不要猜测时长限制、下载权限或让用户重复提供已有音源。'} if isinstance(error,SingingFailure) else {}
