# DSH Singing · 本地 AI 翻唱

**让 DeepSeek Harness 在 QQ 里唱出来：找到原曲、保留旋律、换成指定音色，再把歌声作为语音发回当前会话。**

[English](README.en.md) · [配置参考](docs/CONFIGURATION.md) · [更新记录](CHANGELOG.md) · [第三方说明](THIRD_PARTY_NOTICES.md)

这是一套从实际部署中整理出来的翻唱后端和 QQ 插件集成。它使用 Demucs 分离人声、Seed-VC 转换音色、RMVPE 检查音高，并通过 OneBot 11 / NapCat 发送语音。这里的“唱歌”是基于原曲音轨的歌声音色转换，不是把歌词交给 TTS 朗读，也不是从零生成一首歌。

## 能做什么

- **QQ 点歌**：私聊和群聊共用 `sing_song` 工具，按当前会话路由。
- **指定起唱位置**：支持原音轨秒数，或从指定歌词开始；同一句重复时可选第几次。
- **尽量唱完整片段**：优先用可用的时间歌词定位乐段；无法确定副歌时可选有歌声的自然片段。通常 30–60 秒，单次最多 90 秒。
- **原曲身份核对**：保留歌名、歌手和版本约束；支持公开可播放音轨、B 站 BV 链接与管理员导入的本地音频。
- **成品优先**：同歌、同音色、同片段命中缓存时直接复用；更改起点、时长、来源或音色会区分处理。
- **保留旋律与调性**：不开自动升降调；转换后检查音高、时序及有效歌声比例。
- **处理间奏和混音**：保守缩短长纯伴奏间奏，保留换气及短停顿；提升人声相对伴奏的音量并限制峰值。
- **发送前复核**：生成结束后再次核对会话、音频路径和质量结果；送达状态未知时不自动重发。
- **共享 GPU 队列**：使用与本地生图模块相同的队列符号；成品缓存命中不占 GPU 队列。

## 仓库内容

```text
cover.py / resolve_song.py       翻唱流水线与音源解析
song_position.py                秒数/歌词定位及识别时间轴缓存
performance_library.py          成品缓存与请求匹配
instrumental_gaps.py             间奏裁剪
singing_mix.py / pitch_check.py  混音与音高检查
integrations/dsh-onebot-qq/      包含翻唱工具的 QQ 插件替换版
patches/seed-vc-offline.patch    固定版本 Seed-VC 的本地加载补丁
models.lock.json                模型来源、版本与 SHA-256
scripts/ / tests/               环境准备与离线回归测试
```

仓库不含歌曲音频、参考声音、模型权重、账号密钥、聊天记录或本地运行缓存。发布副本将原部署中的个人目录改成了环境变量，生产实例不会被安装步骤自动修改。

## 运行条件

当前目标环境是 **Windows + NVIDIA CUDA**。原部署使用 Python 3.11、PyTorch 2.4.1 / CUDA 12.1 和 Node.js 22 以上；Linux/macOS 尚未验证，代码含 Windows 子进程及路径处理。

还需要 Git、FFmpeg、DeepSeek Harness、能正常收发消息的 OneBot 11 / NapCat，以及一段获准使用的清晰参考人声。翻唱后端没有固定显存保证；首次处理通常明显慢于成品缓存命中。

**这是后端 + QQ 插件集成包**，目前不是在任意 DSH 上点一下就能完成全部模型和 GPU 环境配置的独立插件。QQ 插件目录包含可分发的 JavaScript 代码及类型声明，不包含上游 TypeScript 开发工程。

## 安装

以下命令在 PowerShell 中运行。路径示例使用用户目录，可换成自己的目录。

### 1. 获取代码和 Python 环境

```powershell
git clone https://github.com/MarcKeee1/dsh-singing.git "$HOME\.dsh\singing"
Set-Location "$HOME\.dsh\singing"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu121
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

锁定文件是原部署的完整依赖快照，包含 CUDA 版本的 PyTorch。先安装上面的 CUDA wheel；若平台或驱动不同，需要自行匹配 PyTorch 发行版。

### 2. 下载并核对模型

```powershell
.\.venv\Scripts\python.exe download-models.py
.\.venv\Scripts\python.exe scripts\prepare-runtime.py --warm-demucs
```

下载器按 `models.lock.json` 的固定版本及 SHA-256 校验 Seed-VC、RMVPE、CAMPPlus、Whisper（含分词器）和 BigVGAN。准备脚本获取固定提交的 Seed-VC，应用本地加载补丁，生成 `singing-local.yml`；`--warm-demucs` 预下载 Demucs。模型准备需要联网，后续本地音频的转换和歌词识别使用本地模型。

### 3. 设置路径和参考声音

把 FFmpeg 和参考人声路径换成实际位置。参考音频以清晰、单人、无背景音乐的约 8 秒人声为宜。

```powershell
$env:DSH_SINGING_ROOT = (Get-Location).Path
$env:DSH_FFMPEG = 'C:\Tools\ffmpeg\bin\ffmpeg.exe'
$env:DSH_SINGING_REFERENCE = 'C:\Audio\my-reference.wav'
$env:DSH_QQ_WORKSPACE = 'C:\Workspaces\qq'
```

以上只设置当前 PowerShell 的环境。**运行 DSH 的进程也必须继承相同配置**：可以在该环境中启动 DSH，或将变量保存为用户环境变量后完全退出并重新启动 DSH。例如：

```powershell
foreach ($name in @('DSH_SINGING_ROOT','DSH_FFMPEG','DSH_SINGING_REFERENCE','DSH_QQ_WORKSPACE')) {
    [Environment]::SetEnvironmentVariable($name, (Get-Item "Env:$name").Value, 'User')
}
```

`DSH_QQ_WORKSPACE` 必须与 QQ 插件绑定的工作区路径一致。使用自定义 DSH 数据目录时另设 `DSH_HOME`。`.env.example` 仅是配置参考，不会自动加载。

已有本地 TTS 桥接器的用户也可以不设置 `DSH_SINGING_REFERENCE`，改用 `DSH_TTS_*` 和 `DSH_VOICE_CONFIG` 生成参考声音；所需接口见[配置参考](docs/CONFIGURATION.md)。普通静态参考音频模式不需要 TTS 账号。

### 4. 安装 QQ 集成版

在仓库根目录打包：

```powershell
npm pack ./integrations/dsh-onebot-qq
```

没有 npm 时，也可运行 `.\.venv\Scripts\python.exe scripts\pack.py` 生成相同布局的安装包。

会得到 `dsh-onebot-qq-0.9.10-singing.8-public.1.tgz`。通过 DSH 当前使用的插件安装流程，将其作为 **同名 `dsh-onebot-qq` 插件的升级包** 安装，保留现有 OneBot 连接、管理员和工作区配置，再重新启动 DSH。

不要额外挂载第二份 QQ 插件，也不要把整个仓库当作普通 npm 插件安装。具体本地包入口可能随 DSH 版本不同；本仓库不自动编辑宿主 profile。若以前没有 QQ 插件，应先把 OneBot/NapCat 通道配置到正常收发消息。

## 怎么用

在已经绑定 QQ 工作区的私聊或群聊中直接说：

| 想做什么 | 示例 |
| --- | --- |
| 点一首歌 | `唱一段任然的《无人之岛》` |
| 从秒数开始 | `唱周杰伦《搁浅》，从 1 分 20 秒开始` |
| 从头开始 | `这次从 0 秒开始唱` |
| 指定歌词起句 | `从“<完整歌词起句>”开始唱`，实际填写至少四个字 |
| 同一句的第二次 | `从这句第二次出现的地方开始` |
| 指定时长 | `只唱 15 秒` |
| 指定版本 | `用这个 BV 链接的版本，从 80 秒开始唱：<完整链接>` |
| 导入音频 | 管理员提供可访问的本地音频路径，再指定片段 |

从秒数开始时，秒数对应本次选中音源**裁剪前**的时间轴；不同 MV/唱片版时间轴可能不同。歌词定位根据实际音轨做本地识别，首次通常更慢；模糊、错字或无法可靠识别的歌词可能定位失败，可以改用秒数。

### `sing_song` 工具参数

| 参数 | 必填 | 含义 |
| --- | --- | --- |
| `song` | 是 | 准确歌名，最长 160 字符 |
| `artist` | 是 | 原唱歌手，最长 80 字符；不省略或偷偷替换歌手 |
| `start_seconds` | 否 | 0–7200 秒；`0` 表示从头，省略表示自动选择 |
| `chorus_hint` | 否 | 用户指定的起唱歌词，至少四个有效字符、最多 120 字符；与秒数互斥 |
| `lyric_occurrence` | 否 | 同句第几次出现，整数 1–10；只与歌词起句一起使用 |
| `duration_seconds` | 否 | 明确要求时填写 5–90 秒；默认自动选择 |
| `source_url` | 否 | 完整 B 站 BV 链接 |
| `source_path` | 否 | 管理员提供、位于允许读取目录的本地音频路径 |

例如，模型可调用：

```json
{"song":"搁浅","artist":"周杰伦","start_seconds":80,"duration_seconds":30}
```

普通群成员可以点歌；本地文件导入需要管理员权限。当前集成版的私人会话也限 QQ 插件配置的管理员，群聊使用当前群的会话映射。

## 缓存与排查

成品、音源和歌词时间轴分别保存在 `performance-cache/`、`song-cache/`、`alignment-cache/`。缓存按请求和音色信息匹配，并校验音频哈希；静态参考文件改变后会生成新的音色签名。

| 现象 | 优先检查 |
| --- | --- |
| 模型看不到 `sing_song` | 集成版是否升级成功、是否重启 DSH、QQ 会话工作区是否匹配 |
| 找不到音源 | 歌名/歌手/版本是否准确；尝试完整 BV 链接或管理员本地音频 |
| 歌词定位失败 | 使用更完整且准确的起句，指定出现次数，或改用秒数 |
| 首次生成慢 | 下载是否完成、GPU 是否忙、是否正在本地识别歌词；缓存命中会快很多 |
| 模型或 FFmpeg 缺失 | 检查 `DSH_SINGING_ROOT`、`DSH_FFMPEG`、准备脚本是否运行成功 |
| 声音不对 | 检查参考音频或本地 TTS 配置；更改音色会区分缓存 |
| 音准检查没过 | 更换含清晰歌声的片段；查看本地 `jobs/<id>/worker.log` 和 `pitch.json` |
| 生成成功但未发送 | 检查 OneBot 连接、当前会话映射、允许媒体目录和文件大小限制 |

请求结果保存在 `requests/*.result.json`，阶段诊断保存在 `jobs/<id>/`。先查本地诊断；不要把含账号配置或私人内容的完整运行目录上传到 issue。

公开音源的可用性会变化；没有可正常取得的音轨时仍会失败。自动音高检查是相对原音轨的技术校验，不能保证任意曲目的人声质量或音色一致性。音源、参考声音与生成结果请在取得相应授权的范围内使用。

## 测试与版本说明

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
npm test
```

测试覆盖音源身份、起点/歌词定位、缓存区分、间奏、混音、发送路由和参数拒绝路径；QQ 发送使用桩，不会向真实群聊或私聊发送测试消息。自动测试不代替新电脑上的完整 GPU 合成与 QQ 验收。

本版来源：本地 `0.9.10-singing.8` 集成快照，公开 QQ 包版本 `0.9.10-singing.8-public.1`。仓库还增加了环境变量配置、可直接提供参考音频的模式、固定模型下载和安装说明。未承诺兼容未验证的 DSH/OneBot 后续版本。

## 许可证与致谢

本仓库按 GPL-3.0 发布；QQ 集成沿用上游 BSD-3-Clause 声明。感谢 [Seed-VC](https://github.com/Plachtaa/seed-vc)、[DSH OneBot QQ](https://github.com/mario841859784/dsh-onebot) 以及 Demucs、RMVPE、Whisper、CAMPPlus、BigVGAN 等项目。模型遵循各自条款，详见[第三方说明](THIRD_PARTY_NOTICES.md)。

由 **MarcKeee1** 维护，**Codex** 协助实现与整理。
