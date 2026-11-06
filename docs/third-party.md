# 第三方来源

项目许可证不替代模型和依赖各自的许可证。权重不随源码或 npm 包发布，安装时从固定的原项目地址获取。

| 组件 | 来源 / 用途 | 发布方式 |
|---|---|---|
| Seed-VC | [Plachtaa/seed-vc](https://github.com/Plachtaa/seed-vc)，音色转换 | 固定提交下载；3 个修改文件在 `vendor-overrides`，保留 GPL-3.0 许可证 |
| OneBot 接口思路 | [mario841859784/dsh-onebot](https://github.com/mario841859784/dsh-onebot)，DSH QQ 发送接口 | 不捆绑完整插件；保留 BSD-3-Clause 来源声明 |
| Demucs / htdemucs | [facebookresearch/demucs](https://github.com/facebookresearch/demucs)，人声/伴奏分离 | Python 依赖和校验后的模型 |
| Seed-VC 权重 | [Plachta/Seed-VC](https://huggingface.co/Plachta/Seed-VC) | 固定 revision / SHA-256 |
| RMVPE | [lj1995/VoiceConversionWebUI](https://huggingface.co/lj1995/VoiceConversionWebUI) | 固定 revision / SHA-256 |
| CAMPPlus | [funasr/campplus](https://huggingface.co/funasr/campplus) | 固定 revision / SHA-256 |
| BigVGAN | [nvidia/bigvgan_v2_44khz_128band_512x](https://huggingface.co/nvidia/bigvgan_v2_44khz_128band_512x) | 固定 revision / SHA-256 |
| Whisper Small | [openai/whisper-small](https://huggingface.co/openai/whisper-small)，内容特征与歌词定位 | 固定 revision / SHA-256 |

Seed-VC 固定提交：`51383efd921027683c89e5348211d93ff12ac2a8`。修改仅涉及：从明确的本地模型目录加载、限制推理上下文/缓存尺寸，以及推理兼容性修复；具体文件及前后哈希在 `vendor.lock.json`。

播放响应中的独立音轨/合并流结构参考了 [yt-dlp 项目自身实现](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/bilibili.py)。本项目未捆绑 yt-dlp，也不借助它绕过访问拒绝。

参考音频由安装者自己提供；仓库不包含个人声音、歌曲音频、歌词时间戳或聊天记录。

## 公开播放器协议参考

新增平台适配参考 yt-dlp 的公开实现描述的正常播放器元数据结构：

- [QQ 音乐歌曲详情与公开播放地址](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/qqmusic.py)

本项目没有打包 yt-dlp，也不提供付费解锁或地域代理。可选的 B 站和网易云登录由用户本人扫码授权，Cookie 仅用于各自官方接口，保存在本机，不进入模型上下文或发布包。

网易云二维码和普通网页请求格式参考 [NeteaseCloudMusicApiEnhanced](https://github.com/neteasecloudmusicapienhanced/api-enhanced) 的公开接口实现；不捆绑或运行该项目的服务。AES/RSA 编码使用 Python 依赖 [PyCryptodome](https://www.pycryptodome.org/) 3.23.0（BSD / Public Domain），直接请求网易云官方 HTTPS 网页接口。

## 0.3.0 和声分离

使用 [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) 0.30.2（MIT）和 [UVR 模型发布库](https://github.com/TRvlvr/model_repo/releases/tag/all_public_uvr_models) 的 `UVR_MDXNET_KARA_2.onnx`。安装器核对权重 SHA-256；运行时使用与该哈希对应的固定参数，不下载可变模型列表。包装层修正该版本 soundfile 写入的目录及声道布局，不修改上游包。依赖与模型遵循各自上游条款，权重不随本包分发。
