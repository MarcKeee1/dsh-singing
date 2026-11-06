# dsh-singing 0.3.2

[简体中文](README.md) · [Changelog](CHANGELOG.md) · [Downloads](https://github.com/MarcKeee1/dsh-singing/releases/latest)

A standalone local singing plugin for DeepSeek Harness. Request a song by title and performer, or provide a Bilibili link, and sing it using a reference voice you configure. Choose the whole song, its chorus, a timestamp, or an opening lyric.

The plugin contains no persona, private conversations, QQ account, API credentials, or preset character voice. It performs voice conversion along the source recording's melody; it does not read lyrics through speech synthesis.

## Plugin settings

Open **dsh-singing** in DSH plugin management. Configure the reference audio, excerpt lengths, automatic octave selection, vocal/music/harmony gains and instrumental-gap handling. Changes apply to subsequent jobs; explicit cached-song selections retain their saved audio. One longest recording per title and artist is shown, with no minimum-duration filter; shorter variants remain available for exact reuse.

## What's new in 0.3.0

- Convert lead and backing vocals separately with one reference voice, preserve overlap timing and check each converted track.
- A separate `dsh-singing` plugin; installing it does not replace the OneBot QQ package.
- Openings, choruses, opening through the first complete chorus, longer excerpts, full songs, and selected starting positions. Ordinary requests default to **45 seconds**; “a bit longer” defaults to **90 seconds**, without transcribing the entire song first. Full conversion is reserved for explicit full-song requests; explicit durations remain available.
- The artist is optional. Prefer the original recording, inspect descriptions when titles omit artist names, and request confirmation before using an unconfirmed or different version.
- If a new source is unavailable, offer the verified cached playlist. Selecting an entry plays its existing audio without synthesis. Successful playback asks the model to stop without extra song or old-voice announcements.
- When low notes dominate and a full octave shift better matches the reference register, conversion may shift up 12 semitones. Pitch QA accounts for this shift; it does not guarantee identical speaking and singing timbre.
- Starting at a timestamp or lyric without specifying duration sings to the end. An unspecified singing mode still defaults to an ordinary excerpt of about 45 seconds.
- Once a complete performance is cached, cut later excerpts from its unedited vocal master without separating or converting it again. Timestamp requests use the original source timeline even when the playback mix has shortened instrumental gaps.
- Source lookup order: **Bilibili → NetEase Music → QQ Music**. An explicitly supplied link keeps the requested version. Bilibili BV links and `b23.tv` shares are supported.
- Prefer official audio, lyric videos, studio and audio-focused sources before MVs. Source titles do not guarantee clean vocals, and samples, backing vocals or separation artifacts can remain.
- Deliver to the current QQ conversation through the existing `qq_send_voice` tool, or generate a local MP3 for desktop use.

## Requirements

- DSH 0.2.1 or later stable 0.2.x releases; the supplied validation specifically used **0.2.1-rc.5**. Other prerelease versions require a compatibility check.
- **Python 3.11**, FFmpeg, and Node.js 22+ for packaging/tests.
- Primarily validated on **Windows + NVIDIA CUDA**. CPU installation is available for compatibility and diagnostics but can be much slower. Linux/macOS have not completed full singing acceptance tests.
- Approximately 2.7 GB of pinned models, plus Python/PyTorch and caches. Reserve at least 20 GB.
- QQ delivery needs an existing OneBot plugin, a connected NapCat, and a `qq_send_voice` tool available in the calling session.

The validated PyTorch combination is 2.4.1 / CUDA 12.1. See the [PyTorch version instructions](https://pytorch.org/get-started/previous-versions/) and [Seed-VC](https://github.com/Plachtaa/seed-vc).

## Installation

### 1. Prepare the local backend

Extract or clone this repository and run the following from its root. Verify that `ffmpeg -version` works first.

```powershell
git clone https://github.com/MarcKeee1/dsh-singing.git
Set-Location dsh-singing
py -3.11 scripts/setup.py
```

Setup creates a separate environment under `~/.dsh/singing`, downloads pinned models and Seed-VC, and checks SHA-256 hashes. It does not change an existing DSH profile or replace OneBot. The plugin does not download models when DSH starts.

If FFmpeg is not on PATH:

```powershell
py -3.11 scripts/setup.py --ffmpeg "D:/Tools/ffmpeg/bin/ffmpeg.exe"
```

For a custom data directory or CPU PyTorch:

```powershell
py -3.11 scripts/setup.py --data-dir "D:/AI/dsh-singing" --torch cpu
```

After an interrupted download, fix connectivity and run setup again. Successfully verified files are reused. Setup retains certificate verification and does not bypass download permissions.

### 2. Configure your reference voice

Provide a clear recording you are authorized to use, preferably 10–20 seconds with little background music. Edit `backend.json` in the data directory:

```json
{"referenceAudio":"D:/Audio/my-reference.wav"}
```

This shows only the field to change: **retain the other fields written by setup**. Installation can finish without a voice reference, but the health check will report that singing is not ready. Reference recordings must be decodable and 3–120 seconds long.

The singing voice follows this file. Update it when changing voices. No MiniMax or other paid TTS account is required, and the plugin does not read credentials from an existing speech service.

Run the health check, adapting the Python path for a custom data directory:

```powershell
& "$env:USERPROFILE/.dsh/singing/.venv/Scripts/python.exe" scripts/doctor.py --full
```

### 3. Install the DSH plugin

Download `dsh-singing-0.3.2.tgz` from [Releases](https://github.com/MarcKeee1/dsh-singing/releases/latest), or build it:

```powershell
npm pack --ignore-scripts
dsh plugin --profile <your-profile> add ./dsh-singing-0.3.2.tgz
```

Replace `<your-profile>` with your CLI profile. The desktop application's `desktop` profile is managed by Electron: use its local plugin installation interface instead of forcing CLI changes to that profile.

Restart DSH. Default backend paths match setup. For a custom installation, configure the existing plugin entry:

```yaml
- id: dsh-singing
  config:
    dataDir: D:/AI/dsh-singing
    configFile: D:/AI/dsh-singing/backend.json
    pythonPath: D:/AI/dsh-singing/.venv/Scripts/python.exe
    delivery: auto
```

Do not insert a second copy. Installing only the `.tgz` is insufficient: Python, models and a reference voice must also be prepared.

## Upgrading from the old 0.1.0 repository release

The previous public release packaged singing inside a replacement `dsh-onebot-qq` package. This release is a **standalone plugin** and does not require replacing your QQ plugin.

If your current QQ package already registers `sing_song`, disable that old singing entry before enabling this plugin, or set this plugin's `toolName` to `sing_song_local`. Do not overwrite your customized OneBot package just to install singing. Existing audio caches from the old integration are not automatically migrated; keep the old data until you have verified the new installation.

The delivered standalone source originally identified itself as 0.1.0. It is published here as **0.2.1** to follow this repository's existing tag. The old `v0.1.0` tag and downloads remain available.

## Usage

| Request | Example |
| --- | --- |
| Full song | “Sing all of Ren Ran's 无人之岛.” |
| Chorus | “Only sing the chorus this time.” |
| Default excerpt | “Sing a passage from 无人之岛 by Ren Ran.” |
| Specific source | “Use this Bilibili card and keep this version.” |
| Timestamp | “Start at 1 minute 20 seconds and sing for 45 seconds.” |
| Lyric occurrence | “Start at this lyric: <at least four meaningful characters>, using its second occurrence.” |

A starting position without duration sings to the end. `full` mode must not also specify a start or excerpt duration. Lyric positioning uses local Whisper and can be slower on the first request. A chorus must be located reliably; a generic passage is not silently labeled as a chorus.

### Tool parameters

| Parameter | Meaning |
| --- | --- |
| `song`, `artist` | Required accurate song title and selected performer/version |
| `mode` | `full`: whole song; `chorus`: reliable chorus; `from`: given start; `excerpt`: ordinary passage |
| `source_url` | User-selected BV/b23.tv, NetEase single or QQ Music single URL |
| `source_path` | Administrator-approved local audio within `allowedSourceRoots` |
| `duration_seconds` | Optional duration of at least five seconds; no 90-second ceiling; omit for `full` |
| `start_seconds` | Start on the unedited source timeline; mutually exclusive with opening lyrics |
| `chorus_hint` | User-supplied opening lyric, at least four meaningful characters |
| `lyric_occurrence` | Occurrence of that lyric, default 1, maximum 10 |

```json
{"song":"无人之岛","artist":"任然","mode":"full"}
```

```json
{"song":"无人之岛","artist":"任然","mode":"from","start_seconds":80}
```

### QQ and desktop delivery

- `delivery: auto` uses the existing `qq_send_voice` tool in a QQ session and returns a file in a desktop session.
- `delivery: file` generates a local MP3 only.
- `delivery: qq` requires an eligible QQ conversation.

QQ delivery supplies only the generated file path and uses the normal DSH tool execution and permission checks. The same request is sent once per turn. Uncertain delivery is not automatically retried; inspect the conversation first.

The default output directory is `DSH_HOME/media/onebot/voice`, or `~/.dsh/media/onebot/voice` without `DSH_HOME`. For another OneBot media root, set `outputDir` to that allowed directory rather than granting access to an entire drive.

## Configuration

Plugin settings find the backend and choose delivery:

| Setting | Purpose/default |
| --- | --- |
| `dataDir` | `DSH_HOME/singing` or `~/.dsh/singing` |
| `configFile` | `backend.json` in that directory |
| `pythonPath` | Backend environment's Python |
| `delivery` | `auto`, `file`, or `qq` |
| `toolName` | `sing_song`; use `sing_song_local` to avoid an existing registration |
| `timeoutMs` | 0 means no plugin-wide generation timer; host limits still apply |

Backend settings in `backend.json` resolve relative paths against that file's directory:

| Field | Purpose |
| --- | --- |
| `dataDir`, `modelsDir`, `vendorDir` | Runtime data, verified models and pinned/patched Seed-VC |
| `referenceAudio`, `outputDir` | Your voice reference and allowed MP3 output directory |
| `ffmpeg` | Executable path or command on PATH |
| `allowedSourceRoots` | Local audio import roots; empty by default; supported files up to 100 MB |
| `comfyUrl` | Optional local ComfyUI URL; disabled by default |
| `unloadComfy` | Allow idle Comfy models to unload; false by default |

The GPU queue uses `Symbol.for('dsh.localGpuQueue.v1')` in the same DSH process. Backend file locks also protect one data directory from simultaneous conversions. An optional Comfy check refuses to interrupt active image work; unloading requires explicitly enabling `unloadComfy`.

## Troubleshooting and limits

| Symptom | What to check |
| --- | --- |
| Python/backend missing | Run setup and make all three plugin paths refer to one installation |
| Voice reference not ready | Configure a decodable 3–120 second `referenceAudio` |
| CUDA unavailable | Driver and PyTorch installation; CPU is available but much slower |
| No usable source | Exact title/performer/version, a source link, or approved local audio |
| Missing `qq_send_voice` | Enable the existing OneBot voice tool or use `delivery: file` |
| Output path rejected | Point `outputDir` at a media root already allowed by OneBot |
| Duplicate singing tool | Disable the legacy entry or change `toolName` |
| Pitch/voiced-coverage check failed | Try a clearer passage containing actual singing; failed output is withheld |
| Modified Seed-VC directory | Back it up and move it aside before reinstalling; setup avoids overwriting edits |

Diagnostics remain in local `jobs/` and `requests/` directories; do not publish runtime data, source recordings or voice references. More Chinese detail is available in [configuration](docs/configuration.md), [validation](docs/validation.md) and [third-party notices](docs/third-party.md).

Source availability varies. QQ Music has offline protocol tests, but the delivery's online search did not obtain an eligible track, so complete online acceptance for that provider is not claimed. No access-denial, paid-content or preview restrictions are bypassed. Merged Bilibili multi-segment streams and automatic selection from multi-part collections are not supported.

Automatic pitch checks compare against the extracted source; they do not guarantee perfect pitch, voice similarity or removal of all backing/sample voices. Full-song processing time grows with duration and remains cancellable. Network/stage timeouts, host limits, and QQ voice/file-size limits still apply.

## Tests and licensing

```powershell
npm test
python -m pip install -r requirements-test.txt
python tests/test_backend.py
npm run check:release
```

Publication regression checks passed **15 Node.js tests and 21 Python tests**. The delivery also records an isolated DSH SDK installation and a 104-second synthetic/private long-track conversion; those are supplied validation records, not new commercial-song or real-QQ acceptance runs performed during publication.

Code is GPL-3.0-only; third-party notices and model-specific terms remain applicable. Models are not bundled. See [LICENSE](LICENSE), [NOTICE](NOTICE) and [third-party notes](docs/third-party.md).

Maintained by MarcKeee1, with implementation and publication assistance from Codex.

## Optional Bilibili sign-in

Use the backend environment to run `scripts/bilibili-login.py --data-dir <your-backend-data-directory>`. Scan the QR code in your own Bilibili app. Credentials remain in the local `.auth` directory and are never included in model messages, QQ messages, or the repository. Authentication is used only for Bilibili API requests, not audio CDNs or unrelated sites. Sign-in does not bypass CAPTCHAs or access restrictions; failures require user action. The window can remove the saved sign-in state.

## Optional NetEase sign-in

For chorus selection on a recording without timed lyrics, the backend may obtain a same-song, same-artist NetEase reference. It maps that timeline only after three separate audio windows confirm the same recording and a stable offset. The selected audio is preserved, the verified alignment is cached by its hash, and mismatched recordings fall back to local transcription. Narrow OST credit annotations are accepted without treating live, DJ or cover versions as studio originals.

Run `scripts/netease-login.py --data-dir <your-backend-data-directory> --scan` with the backend environment (`pythonw` on Windows). Scan and confirm using your own NetEase Cloud Music app. The window also checks and removes the saved session. Windows credentials use current-user DPAPI; other systems use a mode-0600 local file. Only official NetEase HTTPS API calls receive the cookies, never media CDNs, other services, QQ or model messages. No DSH restart is needed.

Search, lyrics and playback requests use the saved account. Playback remains subject to the account's normal access; previews and incomplete audio are rejected. Explicit NetEase song links, including `/#/song?id=...`, select NetEase directly. Automatic provider order remains Bilibili, NetEase, QQ Music. Closing the window or expiry stops QR polling. `--status` reports validity without exposing account details or credentials. Do not publish `.auth`.

If the QR endpoint returns verification code 8821, use the official-web sign-in button or `--web`. An existing DSH Electron runtime opens an isolated official NetEase window for user-operated login and verification. It reads only that window's NetEase session, never another browser's profile. Browser cookies are in memory; only the protected backend session is retained after closing. Set `DSH_SINGING_ELECTRON` if the existing runtime is not in the usual DSH home directory.

## Upgrading from 0.2.x

Update the source and rerun `scripts/setup.py` before installing the new package. The installer adds a separate `.venv-lead` environment and a checksum-pinned 53 MB KARA2 model, keeping ONNX/protobuf dependencies isolated from the singing environment. Old data is retained; the new pipeline uses a different voice/cache fingerprint. Dual-track conversion costs more compute, while verified stems and pitch features are reused.
