# 发布指南

发布对象是本仓库源码和 `npm pack` 生成的安装包。运行中的后端数据目录、参考声音、下载歌曲、缓存和聊天数据都不属于仓库。

## 本地检查

```powershell
npm test
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -p "test_*.py"
npm run check:release
npm pack --ignore-scripts --pack-destination ../artifacts
```

最后一条之前先建立 `../artifacts` 目录。不要把压缩包写入仓库根目录后再做源码打包。安装包只包含 `package.json` 中的 files 白名单。

Python 后端需另外运行 `scripts/setup.py`。运行健康检查后，使用自己允许提供的音频验证：生成、音准检查、整首缓存、指定起点剪切、取消任务和输出路径。QQ群发送必须由使用者在自己的会话验收；离线发送测试不能证明平台已送达。

## GitHub

1. 在 GitHub 建立空仓库，将源码目录作为仓库根目录。
2. 先运行发布检查，再提交代码。检查将拒绝私人路径、凭据特征、音频和模型文件。
3. 填写自己的仓库 URL 后再添加 remote、push；此模板没有预设任何人的账号。
4. 发布版本标签 `v0.3.0`，在 Release 上传 `.tgz` 和 SHA-256 校验值。

本地检查不能替代人工审阅新增文件，尤其不要上传运行数据、配置中的凭据或参考音频。

## 音源维护

查询顺序在 `python/resolve_song.py` 的 `PROVIDER_ORDER`。已有音色与版本相同的完整歌声缓存优先，不会因为调整查询顺序而强制重唱。

QQ音乐新增适配参考公开播放器元数据结构，协议依据见 [第三方说明](third-party.md)。平台访问失败时记录实际失败阶段，不更换歌手或绕过限制。

完整歌声缓存保留未剪间奏的母带及校验值；播放版可缩短间奏。指定秒数、歌词或副歌永远在原音轨时间线上定位，之后才处理该片段的间奏。改音色后旧歌声不会冒充新音色。
