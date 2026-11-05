# 更新记录 / Changelog

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
