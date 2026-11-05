# DSH Singing · Local AI Covers

**Let DeepSeek Harness sing in QQ: find the source recording, preserve its melody, convert the voice, and send the result back to the current conversation.**

[简体中文](README.md) · [Configuration](docs/CONFIGURATION.md) · [Changelog](CHANGELOG.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)

This repository packages a deployed singing backend and its QQ integration. Demucs separates the vocals, Seed-VC converts the voice, RMVPE checks pitch, and OneBot 11 / NapCat delivers the audio. It performs singing voice conversion from an existing recording; it neither reads lyrics through TTS nor composes a song from scratch.

## Features

- **QQ song requests:** a shared `sing_song` tool for private and group conversations, routed to the current session.
- **Start from a timestamp or lyric:** select a position on the actual source recording, including a specific occurrence of a repeated lyric.
- **Natural excerpts:** use timestamped lyrics where available; fall back to a passage containing vocals when a chorus cannot be established. Excerpts are usually 30–60 seconds, with a 90-second maximum.
- **Source identity checks:** retain the requested title, original artist and version constraints. Support publicly playable sources, Bilibili BV links, and local audio imported by an administrator.
- **Finished recording cache:** reuse a matching song, voice and excerpt; distinguish changes to position, duration, source or voice.
- **Melody and key preservation:** no automatic transposition; check pitch, timing and voiced coverage after conversion.
- **Mixing and instrumental gaps:** conservatively shorten long instrumental breaks, retain breaths and short pauses, raise vocal presence and limit peaks.
- **Send-time verification:** recheck the current session, output path and quality status. Do not automatically resend when delivery is uncertain.
- **Shared GPU scheduling:** use the same queue symbol as the local image module. Finished cache hits bypass that queue.

## Repository layout

```text
cover.py / resolve_song.py       Pipeline and source resolution
song_position.py                Timestamp/lyric positioning and alignment cache
performance_library.py          Finished recording cache
instrumental_gaps.py             Instrumental gap editing
singing_mix.py / pitch_check.py  Mixing and pitch checks
integrations/dsh-onebot-qq/      Replacement QQ package with singing support
patches/seed-vc-offline.patch    Local-loading patch for a pinned Seed-VC revision
models.lock.json                Model origins, revisions and SHA-256 checksums
scripts/ / tests/               Setup and offline regression tests
```

Songs, reference voices, model weights, credentials, chat history and runtime caches are excluded. Personal deployment paths have been replaced with configurable paths in this publication copy. Setup does not automatically modify an existing production profile.

## Requirements

The current target is **Windows with an NVIDIA CUDA GPU**. The original deployment used Python 3.11, PyTorch 2.4.1 / CUDA 12.1 and Node.js 22 or later. Linux/macOS are unverified; the code includes Windows process and path handling.

You also need Git, FFmpeg, DeepSeek Harness, a working OneBot 11 / NapCat connection, and a clear voice reference you are authorized to use. There is no fixed VRAM guarantee. First-time generation is substantially slower than reusing a finished recording.

**This is a backend plus QQ integration package.** It is not a one-click standalone plugin that installs every model and GPU dependency. The QQ package contains distributed JavaScript and declarations, rather than the upstream TypeScript development tree.

## Installation

Run the following in PowerShell. The example checkout location can be changed.

### 1. Get the code and create a Python environment

```powershell
git clone https://github.com/MarcKeee1/dsh-singing.git "$HOME\.dsh\singing"
Set-Location "$HOME\.dsh\singing"
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch==2.4.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu121
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

The lock file is the full dependency snapshot from the original environment, including CUDA-tagged PyTorch. Install the CUDA wheels above first. A different platform or driver may require a matching PyTorch distribution.

### 2. Download and verify models

```powershell
.\.venv\Scripts\python.exe download-models.py
.\.venv\Scripts\python.exe scripts\prepare-runtime.py --warm-demucs
```

The downloader verifies the pinned revisions and SHA-256 checksums in `models.lock.json` for Seed-VC, RMVPE, CAMPPlus, Whisper including its tokenizer, and BigVGAN. Setup obtains the pinned Seed-VC source, applies the local-loading patch and writes `singing-local.yml`. `--warm-demucs` downloads Demucs in advance. Preparation needs the network; conversion and lyric recognition for local audio use local models afterward.

### 3. Configure paths and a reference voice

Replace the FFmpeg and reference paths below. A clear, single-speaker voice sample of about eight seconds without background music is recommended.

```powershell
$env:DSH_SINGING_ROOT = (Get-Location).Path
$env:DSH_FFMPEG = 'C:\Tools\ffmpeg\bin\ffmpeg.exe'
$env:DSH_SINGING_REFERENCE = 'C:\Audio\my-reference.wav'
$env:DSH_QQ_WORKSPACE = 'C:\Workspaces\qq'
```

These variables affect only the current PowerShell process and its children. **The DSH host must inherit the same configuration.** Launch it from that environment, or save user environment variables and fully exit/restart DSH:

```powershell
foreach ($name in @('DSH_SINGING_ROOT','DSH_FFMPEG','DSH_SINGING_REFERENCE','DSH_QQ_WORKSPACE')) {
    [Environment]::SetEnvironmentVariable($name, (Get-Item "Env:$name").Value, 'User')
}
```

`DSH_QQ_WORKSPACE` must match the workspace bound to the QQ connection. Set `DSH_HOME` when using a custom DSH data directory. `.env.example` is a reference and is not automatically loaded.

If you already have a compatible local TTS bridge, leave `DSH_SINGING_REFERENCE` unset and use `DSH_TTS_*` / `DSH_VOICE_CONFIG` instead. The required interface is documented in [Configuration](docs/CONFIGURATION.md). A static reference does not require a TTS account.

### 4. Install the QQ integration

From the repository root:

```powershell
npm pack ./integrations/dsh-onebot-qq
```

Without npm, run `.\.venv\Scripts\python.exe scripts\pack.py` to build a tarball with the same package layout.

This creates `dsh-onebot-qq-0.9.10-singing.8-public.1.tgz`. Install it through your DSH version's existing local plugin workflow as an **upgrade of the same `dsh-onebot-qq` package**. Retain the existing OneBot connection, administrators and workspace configuration, then restart DSH.

Do not mount a second QQ plugin instance or install the repository root as a regular npm plugin. Local package installation controls vary between DSH versions; this project does not automatically edit the host profile. If QQ is not already configured, first establish a working OneBot/NapCat channel.

## Usage

Ask in a private or group QQ conversation attached to the configured workspace. Requests can be phrased naturally, for example:

| Goal | Example |
| --- | --- |
| Request a song | `Sing a passage from Ren Ran's “无人之岛”.` |
| Start at a timestamp | `Sing Jay Chou's “搁浅”, starting at 1 minute 20 seconds.` |
| Start at the beginning | `This time, start at 0 seconds.` |
| Start from a lyric | `Start from “<complete lyric phrase>”.` Use at least four meaningful characters. |
| Repeated lyric | `Start from the second occurrence of that line.` |
| Short excerpt | `Only sing 15 seconds.` |
| Specific version | `Use this BV version and start at 80 seconds: <full URL>.` |
| Local recording | An administrator supplies an accessible local audio path and selects an excerpt. |

Timestamps refer to the selected source's timeline **before editing**. An MV and an album recording may have different timelines. Lyric positioning transcribes the actual audio locally; the first request can take longer. Unclear or incorrectly quoted lyrics may not match reliably; use a timestamp when necessary.

### `sing_song` parameters

| Parameter | Required | Meaning |
| --- | --- | --- |
| `song` | Yes | Exact title, up to 160 characters |
| `artist` | Yes | Original artist, up to 80 characters; never silently omitted or replaced |
| `start_seconds` | No | 0–7200; `0` explicitly starts at the beginning; omission selects automatically |
| `chorus_hint` | No | User-provided opening lyric, at least four meaningful characters and at most 120; mutually exclusive with timestamp |
| `lyric_occurrence` | No | Integer 1–10, only with an opening lyric |
| `duration_seconds` | No | 5–90 seconds when explicitly requested; otherwise automatic |
| `source_url` | No | Full Bilibili BV video URL |
| `source_path` | No | Administrator-provided local audio within allowed media roots |

Example tool call:

```json
{"song":"搁浅","artist":"周杰伦","start_seconds":80,"duration_seconds":30}
```

Group members can request songs. Importing local files requires administrator status. The current integration also limits private conversations to administrators configured in the QQ plugin; group delivery follows the current group's session mapping.

## Caching and troubleshooting

Finished recordings, source audio and lyric alignments live in `performance-cache/`, `song-cache/` and `alignment-cache/`. Cache entries match the request and voice signature and validate the audio hash. Changing a static reference file changes its voice signature.

| Symptom | Check first |
| --- | --- |
| `sing_song` is unavailable | Integration package installed, DSH restarted, and QQ workspace path matches |
| No playable source | Exact title, artist and version; try a full BV link or administrator-provided local audio |
| Lyric matching fails | Use a longer accurate phrase, select its occurrence, or supply a timestamp |
| First generation is slow | Model setup, GPU workload and local lyric recognition; finished hits are faster |
| Missing model or FFmpeg | `DSH_SINGING_ROOT`, `DSH_FFMPEG` and setup completion |
| Wrong voice | Reference audio or local TTS configuration; voice changes separate cache entries |
| Pitch check fails | Select a clearer vocal passage; inspect `jobs/<id>/worker.log` and `pitch.json` locally |
| Generated but not delivered | OneBot connection, current session mapping, media roots and file size limits |

Request results are written to `requests/*.result.json`; stage diagnostics stay in `jobs/<id>/`. Read local diagnostics first. Do not attach a complete runtime directory containing credentials or private content to an issue.

Public source availability changes. A request can still fail when no normally playable source is available. Automatic pitch checks compare technical measurements with the original track; they do not guarantee quality or voice similarity for every song. Use sources, reference voices and generated recordings within your authorization.

## Tests and version

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
npm test
```

Tests cover source identity, timestamp/lyric positioning, cache discrimination, gaps, mixing, routing and rejected parameters. QQ delivery is stubbed; tests send no messages to real people or groups. Automated checks do not replace full GPU synthesis and QQ acceptance on a new machine.

This publication derives from the locally deployed `0.9.10-singing.8` integration; the public QQ package is `0.9.10-singing.8-public.1`. Publication changes add configurable paths, a direct reference-audio mode, pinned model downloads and setup documentation. Compatibility with untested future DSH/OneBot releases is not promised.

## License and acknowledgements

The repository is published under GPL-3.0. The QQ integration retains its upstream BSD-3-Clause notice. Thanks to [Seed-VC](https://github.com/Plachtaa/seed-vc), [DSH OneBot QQ](https://github.com/mario841859784/dsh-onebot), Demucs, RMVPE, Whisper, CAMPPlus and BigVGAN. Models retain their own terms; see [Third-party notices](THIRD_PARTY_NOTICES.md).

Maintained by **MarcKeee1**, with implementation and publication preparation assisted by **Codex**.
