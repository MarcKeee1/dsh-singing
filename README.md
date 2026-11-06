# dsh-singing 0.3.0

[English](README.en.md) · [更新记录](CHANGELOG.md) · [下载](https://github.com/MarcKeee1/dsh-singing/releases/latest)

DeepSeek Harness（DSH）的独立本地唱歌插件。输入歌名、歌手或 B 站分享卡片，用自己配置的参考音色唱一段歌曲；也可以从指定秒数或歌词开始。

插件只提供唱歌功能，不附带人格、私人聊天记录、QQ 账号、API 密钥或预设人物音色。

## 插件页设置

安装后在 DSH 的插件管理中找到 **dsh-singing**，打开配置即可调整参考音频路径、普通/加长片段时长、自动升八度、人声/伴奏/和声音量和长间奏处理。另有发送方式、后端路径和超时设置。保存配置后用于后续任务；运行中的任务沿用启动时配置。

设置改变会区分新合成的缓存；显式点选已有歌单仍播放原缓存，不会偷偷重唱。歌单同一歌名和歌手只显示时长最长的一份，其他片段保留用于精确点播；没有“短于30秒就隐藏”的规则。

## 功能

- 支持只唱开头、副歌、开头到完整副歌、长一点、完整版和指定起点。普通点歌默认约 **45 秒**，“长一点”默认约 **90 秒**；这两种模式不先转写整首歌词。只有明确要求整首才使用完整版，指定时长仍按指定值处理。按原音源旋律做音色转换。
- 歌手可省略，自动搜索尽量确认原唱；无法确认原唱或只有其他版本时先返回候选，确认后使用。标题没写歌手时会参考简介；明确提供的链接保留该版本。
- 无法取得新音源时返回已缓存歌单；用户选序号后直接播放缓存，不重新合成。成功发出歌声后不补发歌名确认或旧音色提醒。
- 将主唱与和声分别转为同一参考音色，保留两条声部的重叠和尾音时间，避免和声没结束就被下一句切断；两条声部分别接受音准检查。
- 使用参考声音确定音色；低音占多数、升八度明显更接近参考音域时可整体升 12 个半音，音准校验会计入该移调。
- 支持完整 BV 链接和 `b23.tv` 短链接；用户明确指定的翻唱、改编版本可用。
- 查找顺序：**B 站 → 网易云 → QQ 音乐**；明确给出原曲链接时只使用指定版本。
- B 站优先官方音频、歌词版、录音室或纯享版，再考虑 MV；自动搜索排除明显对白、解说和现场版本。
- 同音色、同版本的成品优先复用。唱过整首后，副歌或指定片段从完整歌声母带直接剪切，不重新分离和合成。
- 指定秒数，或在实际音轨上识别并定位至少四个字的起唱歌词。
- 保守缩短较长间奏、增强人声；音准和有效歌声检查不通过时不发送。
- 桌面会话生成 MP3；QQ 会话通过现有 OneBot 的 `qq_send_voice` 发到当前聊天。

这是 **DSH 插件 + 本地 Python 后端**。首次使用需要安装后端和模型；只安装 `.tgz` 不会自动具备模型环境。插件不会在启动时偷偷下载模型。

## 环境

- DSH 0.2.1 或后续 0.2.x 稳定版；当前验证版本：0.2.1-rc.5。其他小版本的预发布版需另行核对兼容性。
- Python **3.11**、FFmpeg；Node.js 22 以上用于打包和测试。
- 首版以 Windows + NVIDIA CUDA 为主要验证环境。CPU 安装选项用于兼容和排查，速度明显较慢；Linux/macOS 尚未做完整歌声实测。
- 固定模型约 2.7 GB，另需 Python/PyTorch 环境和缓存空间，建议至少预留 20 GB。
- QQ 发送需要现有的 OneBot 插件、已连接的 NapCat，以及当前会话可调用的 `qq_send_voice`。

PyTorch 使用已验证的 2.4.1 / CUDA 12.1 组合，安装命令参考 [PyTorch 官方版本说明](https://pytorch.org/get-started/previous-versions/)。模型转换基于 [Seed-VC](https://github.com/Plachtaa/seed-vc)。

## 安装

### 1. 准备本地后端

解压或克隆本仓库，在仓库根目录运行。先确认 `ffmpeg -version` 能执行：

```powershell
py -3.11 scripts/setup.py
```

安装器会在 `~/.dsh/singing` 创建唱歌 `.venv` 和和声分离 `.venv-lead` 两个独立虚拟环境、下载固定版本模型和 Seed-VC，并逐项校验 SHA-256。不会修改已有 DSH profile，也不会替换 OneBot 插件。

FFmpeg 不在 PATH 时：

```powershell
py -3.11 scripts/setup.py --ffmpeg "D:/Tools/ffmpeg/bin/ffmpeg.exe"
```

指定数据位置或 CPU 版 PyTorch：

```powershell
py -3.11 scripts/setup.py --data-dir "D:/AI/dsh-singing" --torch cpu
```

模型安装失败时修复网络后重跑；已校验成功的文件会复用。安装器保留证书检查，不绕过下载权限。模型默认从原项目提供的地址获取。

### 2. 设置参考音色

准备一段你有权使用的清晰说话录音，建议 10–20 秒，少背景音乐。编辑数据目录中的 `backend.json`：

```json
{
  "referenceAudio": "D:/Audio/my-reference.wav"
}
```

这里只展示需要修改的字段，**保留安装器写入的其他字段**。没有提供参考音频时，安装可以完成，但健康检查会明确显示未就绪。

音色跟随这个文件；如果更换了说话音色，请同时更新参考文件。本插件不依赖 MiniMax 或其他付费 TTS 账号，也不会读取已有语音服务的密钥。

运行健康检查；自定义目录时替换路径：

```powershell
& "$env:USERPROFILE/.dsh/singing/.venv/Scripts/python.exe" scripts/doctor.py --full
```

全部检查通过后再安装 DSH 插件。

### 3. 安装 DSH 插件

使用发布页的 `dsh-singing-0.3.0.tgz`，或者自己打包：

```powershell
npm pack --ignore-scripts
dsh plugin --profile <你的profile名> add ./dsh-singing-0.3.0.tgz
```

将 `<你的profile名>` 替换为实际 CLI profile。桌面版的 `desktop` profile 由 Electron 管理，请使用桌面插件管理入口安装本地包，不要用普通 CLI 强行改它。

重启 DSH。默认后端路径与默认安装器一致。自定义数据目录时，在插件设置里配置：

```yaml
- id: dsh-singing
  config:
    dataDir: D:/AI/dsh-singing
    configFile: D:/AI/dsh-singing/backend.json
    pythonPath: D:/AI/dsh-singing/.venv/Scripts/python.exe
    delivery: auto
```

这是已有 `dsh-singing` 条目的覆盖示例，不要重复插入两份插件。

如果当前 QQ 插件已经自带 `sing_song`，先停用旧唱歌入口，或者把本插件 `toolName` 设为 `sing_song_local`。不要为了安装本插件覆盖自己修改过的整个 OneBot 包。

## 从仓库旧版 0.1.0 升级

此前公开的 `v0.1.0` 将唱歌功能集成在同名 OneBot 替换包中；本版改为独立 `dsh-singing` 插件。安装新包不需要替换 QQ 插件，但启用前要处理旧 `sing_song` 重名：停用旧唱歌入口，或先将新插件工具名设为 `sing_song_local`。

旧集成版的缓存不自动迁移。完成新安装验收前请保留旧数据。桌面交付源码原标记为 0.1.0，为接续仓库已有标签，本次公开包统一使用 **0.2.1**；旧 `v0.1.0` 标签和下载保留。

## 使用示例

- “把任然《无人之岛》整首唱完。”
- “这次只唱《无人之岛》的副歌。”
- “唱任然《无人之岛》的一段。”
- “按这张 B 站卡片唱，保留这个版本。”
- “从 1 分 20 秒开始唱，唱 45 秒。”
- “从这句歌词开始：……，唱第二次出现的那一段。”

指定起点而未指定时长时，从该处唱到结尾。整首模式不同时指定片段时长或起点。

歌词起句至少四个字；歌词定位使用本地 Whisper，首次会更慢。副歌依据实际音轨中的重复歌词段或该版本可靠时间轴定位；找不到可靠范围会报错。完整缓存保留未删间奏的原始时间轴，因此后续“从 80 秒开始”不会因播放版剪过间奏而错位。

## 可选 B 站登录

在插件目录运行，数据目录必须与唱歌后端一致：

```powershell
& "$env:USERPROFILE/.dsh/singing/.venv/Scripts/pythonw.exe" scripts/bilibili-login.py --data-dir "$env:USERPROFILE/.dsh/singing"
```

点击“扫码登录”，用自己的 B 站 App 扫码并在手机确认。窗口不会询问密码、向 QQ 发送二维码或把 Cookie 交给模型。只有正常的 B 站 API 请求使用本机登录状态，音频 CDN 和其他平台不接收它；异常跨站跳转会停止。Linux 可用虚拟环境的 `python` 打开同一脚本，需要系统 Tk 支持，凭据文件权限为当前用户读写。

登录不保证解除风控。二维码失效、验证码或访问拒绝会停止，需要用户主动处理；不轮换账号、地址或伪装设备重试。点“退出插件登录”删除本机保存的状态。不要上传数据目录中的 `.auth` 文件夹。

网页版流程参考 [B 站扫码登录接口说明](https://github.com/bilibili-plugins/bilibili-api-collect/blob/master/docs/login/login_action/QR.md)；可在 [B 站官方登录页](https://account.bilibili.com/login) 手动处理验证。官方网页登录与此插件的独立登录状态并不自动同步。

## QQ 和桌面输出

`delivery: auto` 在 QQ 会话中调用已有的 `qq_send_voice`，只传生成文件路径，不传其他聊天目标。调用走 DSH 正常工具执行流程，保留现有权限检查。

`delivery: file` 只生成本地 MP3，适合桌面使用或先试听。`delivery: qq` 要求当前是可发送语音的 QQ 会话。

安装器默认输出到 `DSH_HOME/media/onebot/voice`（未设置时为 `~/.dsh/media/onebot/voice`）。如果你的 OneBot 使用其他媒体目录，请将 `backend.json` 的 `outputDir` 指向其允许发送的目录，**不要为了发音频放开整块磁盘**。

同一回合的相同请求只发送一次。发送结果不确定时不自动重发，先查看聊天记录。

## 配置与维护

完整说明见 [配置和故障排查](docs/configuration.md)。开源与模型来源见 [第三方说明](docs/third-party.md)。发布检查见 [发布指南](docs/releasing.md)，实测范围见 [验证记录](docs/validation.md)。

```powershell
npm test
py -3.11 tests/test_backend.py
npm run check:release
```

Python 测试需要 `requirements-test.txt` 中的轻量依赖，或者直接使用安装好的后端虚拟环境。

## 能力边界

QQ 音乐新增适配已做离线协议测试，平台在线可用性以实际返回为准；这不等于每个平台每首歌都能读取。公开音源查找受平台可用性影响，会员、付费、访问拒绝、试看和受保护资源不会强行绕过。当前不拼接 B 站多段合并流，也不从合集自动挑分 P。

音准检查是相对于提取出的原音源音高，并不保证任何歌曲绝不跑调或听感与说话完全一致。副歌定位不能保证每首都成功；失败会请用户指定起句或秒数。整首合成耗时随歌长增加，默认不设总处理计时器，仍可取消；网络和单阶段故障保护超时保留。QQ 自身的单条语音和文件大小限制仍适用。

## 许可证

项目代码按 GPL-3.0-only 发布。第三方代码保留原许可证；模型权重各自适用其来源项目的条款，未打包到本仓库。参见 [LICENSE](LICENSE)、[NOTICE](NOTICE) 和 [第三方说明](docs/third-party.md)。

## 从 0.2.x 升级

更新源码并重新运行 `scripts/setup.py`，补齐独立分离环境和约53 MB的 KARA2 模型，再安装新 `.tgz`。配置和旧缓存保留；旧版转换结果不会冒充新版音色管线。参考音频和模型不包含在安装包内。双声部增加了计算量；已验证的分离结果和音高特征可复用。
