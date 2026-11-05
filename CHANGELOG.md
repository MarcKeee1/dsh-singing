# 更新记录 / Changelog

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
