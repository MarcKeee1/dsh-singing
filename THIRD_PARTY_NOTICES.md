# Third-party notices / 第三方说明

| Component / 组件 | Source / 来源 | License / 许可证 |
| --- | --- | --- |
| Seed-VC | https://github.com/Plachtaa/seed-vc | GPL-3.0; pinned commit `51383efd921027683c89e5348211d93ff12ac2a8` |
| DSH OneBot QQ | https://github.com/mario841859784/dsh-onebot | BSD-3-Clause; copyright retained in `integrations/dsh-onebot-qq/LICENSE` |

`patches/seed-vc-offline.patch` modifies the pinned Seed-VC revision for local model loading and bounded inference context. The upstream checkout is fetched separately by the preparation script; model weights are not distributed in this repository.

`patches/seed-vc-offline.patch` 为固定版本 Seed-VC 增加本地模型加载和受限推理上下文。准备脚本单独获取上游源码；本仓库不分发模型权重。

The OneBot integration retains upstream code and its BSD notice. Its singing adapter, speech adapter and runtime registration reflect the locally deployed integration, with machine-specific paths made configurable for publication. Other original OneBot features remain part of that replacement package.

OneBot 集成保留上游代码与 BSD 声明；翻唱适配器、语音适配器和工具注册取自本地部署版本，并将本机路径改为可配置项。同名替换包仍包含 QQ 插件原有功能。

Demucs, RMVPE, Whisper, CAMPPlus, BigVGAN and Python/Node dependencies retain their respective upstream licenses. The download lock records model origins and revisions; check each model's own terms before using or redistributing it. FFmpeg and PyTorch are installed separately.

Demucs、RMVPE、Whisper、CAMPPlus、BigVGAN 及 Python/Node 依赖沿用各自上游许可证。模型锁定文件记录来源与版本；使用或分发模型时请查看对应模型的条款。FFmpeg 和 PyTorch 另行安装。

Repository maintained by MarcKeee1; implementation and publication preparation assisted by Codex.

仓库由 MarcKeee1 维护，Codex 协助实现与发布整理。
