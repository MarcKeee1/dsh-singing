# 更新记录 / Changelog

## 0.3.4 — Verified lyric timeline / 副歌歌词时间轴对齐

- 选定音轨缺少歌词时间轴时，查询同歌名、同歌手的网易云原版参考；在实际音频的三个不同位置校验录音和稳定时间差后，才映射歌词时间轴，保留用户选定的音轨。
- 拒绝不同录音、插入间奏或不稳定时间差的对齐；无可靠参考时继续使用该音轨自身的本地识别。通过核验的结果按音源哈希缓存。
- 电视剧/电影等《作品名》主题曲、片尾曲说明不再误判为不同演唱版本；Live、DJ、翻唱等限定继续参与版本判断。
- 副歌重复检测保留有相邻可靠时长的零时长词，避免丢失识别出的歌词；不会仅凭全部为点时间戳的文本确认副歌。
- Verify the selected recording before borrowing a timed lyric reference, cache the source-specific timeline, and recognize narrow OST title annotations.

## 0.3.3 — NetEase sign-in / 网易云扫码登录

- 新增网易云扫码登录窗口、登录有效性检查和退出入口；本机会话在 Windows 使用 DPAPI 加密，不交给模型或 QQ。
- 扫码遇到 8821 验证时，提供独立的官方网页登录窗口，由用户自行完成验证；不读取其他浏览器的资料。
- 网易云查歌、歌词和播放地址请求实际使用已保存账号；试听继续拒绝，完整音轨继续核对实际时长。
- 支持网易云常见的 `/#/song?id=...` 链接；不再仅凭歌曲收费分类误拒绝平台已授权完整播放的结果。
- 每次点歌独立判断 B 站访问结果，不读取或写入旧的半小时锁定状态；明确识别服务器返回的访问拒绝。
- User-operated NetEase QR sign-in, locally protected sessions, authenticated song lookup and ordinary account-authorized playback.

## 0.3.2 — Full-song intent and source reuse / 完整版意图与原音源复用

- 混合音域歌曲也逐句判断0/+12：不再要求整首先被判为升八度，低音句与高音句分别处理。支持旧版分句记录，关闭自动八度时保留原调。
- “完整版”“完整版本”“整首”“全曲”“全部唱完”统一为 full；不能直接拿片段缓存代替。选择短缓存并要求整首时，保留该版本的歌名、歌手与来源。
- 优先复用已成功演唱且哈希核验通过的完整原音源，减少重复搜索；明确指定的新版本与不同歌手仍严格区分。
- 返回实际失败阶段和原因，区分有效人声不足、分离、换声与音准失败，不根据歌长猜测。
- 较大的长歌结果 JSON 不再被截断为无效响应；保留完整结果并设置明确的资源边界。
- Full-song wording and cached-excerpt protection, verified original-source reuse, stage-specific failures, and complete long-song result capture.

## 0.3.1 — Phrase register / 分句八度判断

- 低音歌曲升八度后，主唱和和声各自检查已经偏高的句子；高音段保持原音域，低音段继续升八度。
- 根据实际音高和参考音域判断，不依赖歌名或歌手；短噪声与颤音不反复切换八度。
- 转换和音准检查使用同一份明确的分句移调记录；局部检查仍不折叠八度，伴奏和时间轴保持原位。
- 主唱与和声分别生成分句记录；关闭自动八度时按原调演唱。新增规则测试覆盖混合音域、和声、颤音、静音和错误记录。
- Check already-high phrases independently for lead and backing vocals before applying an octave lift; verify against the recorded per-phrase target without octave folding.

## 0.3.0 — Configurable dual-vocal singing / 可配置双声部演唱

- DSH 原生插件配置：参考音频、默认时长、自动八度、三种音量和间奏开关；设置传递到实际工作进程并纳入缓存指纹。
- 主唱和和声分别转换、校验与混音，保留重叠尾音时间；新歌自动判断低音是否需要升八度。
- 歌单同一歌名和歌手只显示最长录音；短版本继续保留用于精确调用，无30秒阈值。
- 复用经过哈希校验的分离音轨和音高特征；同一任务复用已加载转换模型。
- 安装脚本新增独立和声分离环境与固定校验的 KARA2 模型，避免 ONNX 与唱歌依赖的 protobuf 冲突。
- Native plugin controls, independently converted/checked lead and harmony, automatic octave selection for new songs, longest-only playlist entries, verified stem/pitch reuse and an isolated separator environment.

## 0.2.1 — Shorter defaults and current backend / 短片段默认值与后端同步

- 普通点歌默认 45 秒，“长一点”默认 90 秒；不先转写整首，也不把长片段延长到完整副歌。 / Default excerpts are 45 seconds and longer excerpts 90 seconds, without whole-song transcription or automatic chorus extension.
- 新增开头、开头到副歌；保留明确的完整版和指定起点。 / Add opening and opening-through-chorus modes, retaining explicit full songs and start positions.
- 同步缓存歌单、可选 B 站扫码登录、歌手可省略及其他版本先确认。 / Sync cached playlists, optional Bilibili sign-in, optional artists and confirmation for alternative versions.
- 同步参考音色、低音占多数时的自动八度判断和音准校验；旧缓存依旧校验音色、版本与音频哈希。 / Sync reference-voice conversion, conditional octave selection and pitch QA while retaining cache integrity checks.
- 24 项 Node.js 和 44 项 Python 测试通过；真实 DSH SDK 的本地集成检查使用模拟发送。 / Passed 24 Node.js and 44 Python tests; local real-SDK integration used mock delivery.

## 0.2.0 — Standalone singing plugin / 独立翻唱插件

- 独立 `dsh-singing` 包，通过已有 `qq_send_voice` 发送；安装不替换 OneBot。 / A standalone package that delivers through the existing voice tool without replacing OneBot.
- 整首、副歌、秒数和歌词起唱；取消此前 90 秒上限。指定起点但省略时长时唱到结尾。 / Full songs, choruses, timestamps and lyric starts; no previous 90-second ceiling. A given start without duration sings to the end.
- 完整歌声母带缓存支持后续剪切，保留原始时间轴。 / Reuse a complete vocal master for later selections, retaining the source timeline.
- 音源顺序 B 站→网易云→QQ 音乐；保留用户指定的版本。 / Bilibili → NetEase → QQ Music lookup while retaining an explicitly selected version.
- 固定版本安装器、模型校验、健康检查，以及双语安装/使用/迁移说明。 / Pinned setup, model checksums, health checks, and bilingual setup/usage/migration documentation.
- 发布前 15 项 Node.js 与 21 项 Python 回归测试通过。 / Publication checks passed 15 Node.js and 21 Python tests.

交付源码原标记为 0.1.0；本次为接续仓库既有标签发布为 0.2.0，不覆盖旧版下载。升级前处理旧 `sing_song` 入口冲突；旧缓存不自动迁移。

The delivered standalone code originally used version 0.1.0. This repository publishes it as 0.2.0 to follow the existing tag, preserving old downloads. Resolve any legacy `sing_song` registration before enabling the new plugin; old caches are not automatically migrated.

## 0.1.0 — Previous public integration / 先前公开集成版

后端加 QQ 插件替换包，片段最长 90 秒。该历史版本继续保存在 `v0.1.0` 标签和 Release。

Backend plus a replacement QQ integration package with excerpts capped at 90 seconds. That historical version remains at the `v0.1.0` tag and release.
