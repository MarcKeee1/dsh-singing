# 配置参考 / Configuration

配置通过环境变量传入；在 DSH 启动前设置。`.env.example` 不会自动加载。

Configure environment variables before launching DSH. `.env.example` is not loaded automatically.

| Variable | 默认值 / Default | 用途 / Purpose |
| --- | --- | --- |
| `DSH_SINGING_ROOT` | Python: 源码目录 / source directory; QQ: `~/.dsh/singing` | 仓库与运行数据目录 / checkout and runtime directory |
| `DSH_HOME` | `~/.dsh` | DSH 数据目录，QQ 音频写入其 `media/onebot/voice` / DSH data and QQ voice output |
| `DSH_FFMPEG` | `ffmpeg` | PATH 中的 FFmpeg，或可执行文件绝对路径 / FFmpeg on PATH or absolute executable path |
| `DSH_SINGING_REFERENCE` | 未设置 / unset | 清晰参考音频，设置后优先使用 / clear voice sample, preferred when set |
| `DSH_QQ_WORKSPACE` | QQ policy 的 `workspacePath`，否则 `~/.dsh/workspaces/qq` | 必须匹配当前会话工作区 / must match the current session workspace |
| `DSH_SINGING_PYTHON` | `<root>/.venv/Scripts/python.exe` | QQ 适配器调用的 Python / Python used by the QQ adapter |
| `DSH_TTS_ROOT` | `<DSH_HOME>/voice-local` | 可选本地 TTS 桥接目录 / optional local TTS bridge directory |
| `DSH_TTS_PYTHON` | `<TTS_ROOT>/.venv-cosy/Scripts/python.exe` | TTS Python interpreter |
| `DSH_TTS_SCRIPT` | `<TTS_ROOT>/tts.py` | TTS adapter script |
| `DSH_VOICE_CONFIG` | `<TTS_ROOT>/minimax.json` | TTS 音色配置，只在无静态参考时需要 / TTS voice settings, required only without a static reference |

## 静态参考 / Static reference

设置 `DSH_SINGING_REFERENCE` 后，后端按参考文件内容生成音色签名，截取最多 8 秒作为转换参考，不调用 TTS 生成参考人声。此变量只影响翻唱；QQ 插件的 `say_voice` 功能仍需要自己的 TTS 服务。

When `DSH_SINGING_REFERENCE` is set, the backend hashes that file for voice identity and uses up to eight seconds as the conversion reference. Reference creation does not invoke TTS. This setting affects singing only; the QQ package's separate `say_voice` feature still needs its own TTS service.

## 已有 TTS 桥接 / Existing TTS bridge

不设置静态参考时，后端读取音色配置中的 `model`、`voice_id`、`speed`、`pitch`、`emotion` 计算缓存签名，不会把整个配置复制到结果。TTS 脚本需要支持：

Without a static reference, the backend hashes `model`, `voice_id`, `speed`, `pitch` and `emotion` from the voice configuration. It does not copy the full configuration into results. The TTS script must support:

```text
python tts.py <text> --out <output.mp3> --json
```

并把音频写入指定位置。QQ 的 `say_voice` 还使用：

The command must write audio to the requested output. The separate QQ `say_voice` adapter also uses:

```text
python tts.py --json -- <text>
```

其标准输出应是 `{"ok":true,"path":"<absolute audio path>"}`。本仓库不附带 TTS 服务、账号配置或 API 密钥。

Its stdout must be JSON such as `{"ok":true,"path":"<absolute audio path>"}`. The TTS service, account settings and API credentials are not bundled.

## 后端独立调用 / Calling the backend directly

创建请求 JSON 后执行 `python cover.py --request <request.json>`。此操作仅生成文件，不发送 QQ。`--cache-only` 只查已完成成品。

Create a request JSON and run `python cover.py --request <request.json>`. This generates a file and does not send it to QQ. `--cache-only` checks finished recordings only.

```json
{
  "title": "My authorized song",
  "artist": "Original artist",
  "source": "C:/Music/my-source.wav",
  "output": "C:/Users/YourName/.dsh/media/onebot/voice/singing-demo.mp3",
  "start": 80,
  "duration": 30,
  "positionVersion": 1
}
```

将示例路径换成实际路径。输出必须是 `DSH_HOME/media/onebot/voice` 目录内的 MP3。省略 `source` 会按 `title`/`artist` 查找公开音源。内部请求字段与 `sing_song` 工具字段不同：`title` 对应 `song`，`start` 对应 `start_seconds`，`duration` 对应 `duration_seconds`。

Replace the sample paths. Output must be an MP3 under `DSH_HOME/media/onebot/voice`. Omitting `source` enables public source lookup by title/artist. Internal request fields differ from tool fields: `title` corresponds to `song`, `start` to `start_seconds`, and `duration` to `duration_seconds`.

## 缓存与 GPU / Cache and GPU

缓存命中会检查音频哈希和质量标记。GPU 队列使用 `Symbol.for('dsh.localGpuQueue.v1')`，只在同一个 DSH 宿主进程内协调；其他生图插件若未使用该符号，不会自动加入这条队列。后端还会检查本机 `127.0.0.1:8188` 的 ComfyUI 队列，有任务时拒绝抢占，空闲时可能请求释放其模型显存。

Cache hits verify audio hashes and quality flags. The shared queue uses `Symbol.for('dsh.localGpuQueue.v1')` within one DSH host process. Other plugins must use that symbol to participate. The backend also checks ComfyUI on local port 8188, refuses to interrupt queued work, and may ask an idle ComfyUI instance to release model memory.
