# Portable executable manual

VideoFlow ships as one console executable per operating system. It contains the
Python runtime, the CLI, the API, the MCP server, the rack UI, presets, and,
when built with the corresponding flags, FFmpeg/FFprobe, whisper.cpp, the
Faster-Whisper runtime plus the small CTranslate2 model, and the Silero VAD
model plus ONNX Runtime.

There is no installer and no Python/Node requirement on the target machine.

| Platform | Artifact | Minimum |
| --- | --- | --- |
| Linux x86_64 | `videoflow-X.Y.Z-linux-x86_64` | glibc from the build host |
| Linux x86_64 | `VideoFlow-X.Y.Z-x86_64.AppImage` | FUSE, or `--appimage-extract-and-run` |
| Windows x86_64 | `videoflow-X.Y.Z-windows-x86_64.exe` | Windows 10/11 x64 |

PyInstaller cannot cross-compile in the usual sense. This project builds the
Linux artifacts natively and the Windows PE locally with Wine WoW64 plus the
Windows embeddable Python. No GitHub Actions workflow is used.

## 1. What the executable does

| Command | Result |
| --- | --- |
| `videoflow version` | Version and platform |
| `videoflow doctor` | FFmpeg/FFprobe, Silero, Faster-Whisper package/model, data directory, UI assets, MCP import |
| `videoflow demo -o DIR` | Generates a 6 s fixture and runs the whole pipeline |
| `videoflow run INPUT -o DIR` | Ingest, Silero/FFmpeg VAD, cuts, J/L, zooms, three NLE exports |
| `videoflow serve` | HTTP API + MCP Streamable HTTP + static rack UI |
| `videoflow mcp` | MCP over stdio for an agent host |

`run` defaults to `--vad-engine auto`: Silero VAD runs when the model and ONNX
Runtime are present, otherwise FFmpeg `silencedetect` takes over. Add
`--transcribe` for offline Faster-Whisper, with whisper.cpp as the automatic
fallback, `--cull-retakes` for transcript-driven culling, or `shorts` for
vertical clips. The LLM retake path is optional.

## 2. Linux

```bash
chmod +x videoflow
./videoflow version
./videoflow doctor
./videoflow demo -o ./videoflow-demo
./videoflow run ~/Videos/interview.mp4 -o ./interview-edit
```

No installation. Keep the binary anywhere and run it. If it is on a read-only
mount, set a writable data directory:

```bash
VIDEOWFLOW_HOME=/home/you/.videoflow ./videoflow serve
```

## 3. Windows

```powershell
.\videoflow.exe version
.\videoflow.exe doctor
.\videoflow.exe demo -o .\videoflow-demo
.\videoflow.exe run "$env:USERPROFILE\Videos\interview.mp4" -o .\interview-edit
```

Notes:

- The binary is unsigned. SmartScreen may warn on first run. Verify the SHA-256
  you downloaded before choosing "More info → Run anyway".
- The console stays attached so progress and JSON reports are visible.
- Paths with spaces are supported; quote them in PowerShell.
- Windows may block an executable downloaded from the internet. Right-click →
  Properties → Unblock, or use `Unblock-File`.
- The data directory defaults to `videoflow-data` next to the executable.
  Override with `set VIDEOWFLOW_HOME=C:\VideoFlowData`.

## 4. Commands in detail

### run

```bash
videoflow run INPUT [-o DIR] [--vad-engine auto|silero|ffmpeg]
                    [--speech-threshold 0.5]
                    [--speech-pad-before-ms 120] [--speech-pad-after-ms 150]
                    [--noise-db -30] [--min-silence-ms 400]
                    [--min-speech-ms 100] [--no-jcuts] [--l-cuts] [--no-zooms]
                    [--offset-ms 200] [--crossfade-ms 20] [--dialect 1.9]
                    [--transcript subs.srt] [--cull-retakes]
                    [--transcribe] [--whisper-engine auto|faster-whisper|whisper.cpp]
                    [--model-size small] [--device cpu|cuda]
                    [--compute-type int8|float16|float32] [--whisper-vad]
                    [--faster-whisper-model DIR] [--whisper-model FILE]
                    [--asr-base-url URL] [--asr-model MODEL] [--asr-language pt]
                    [--llm-base-url URL] [--llm-model MODEL]
                    [--strictness balanced] [--retake-strategy keep_last]
```

Default output is `INPUT-stem-videoflow` next to the source.

Writes:

```
DIR/
  project_state.json
  run.json
  work/source.wav           # analysis PCM at the source audio rate
  work/vad.wav              # only when Silero runs; 16 kHz mono
  work/transcribe.wav       # full-source 16 kHz WAV for local transcription
  exports/timeline.fcpxml   # Resolve
  exports/timeline.xml      # Premiere
  exports/timeline.kdenlive # Kdenlive
```

`run.json` is the machine-readable report: media info, `vad_engine`, speech
interval count, VAD threshold and pads, segment counts, transcript/retake counts,
warnings, artifact paths, PCM digest, and elapsed time.

### Shorts

Shorts can run inside a job (API/UI card) or as a standalone command:

```bash
videoflow shorts interview.mp4 --transcript interview.srt -o shorts-out \
  --count 3 --min-sec 30 --max-sec 60
```

In a job, set `shorts=true` with the SRT and the count/duration bounds. The
`shorts` stage reports progress and logs, and `job.result.shorts` lists the MP4s.

Each clip is rendered at 1080x1920 with center crop and burned-in captions. Use
`--no-subtitles` to skip ASS generation and `--cull-retakes` to remove exact
repeats or LLM-selected retakes first. The report is `shorts-out/shorts.json`.

### Speech-to-text

With no SRT and no ASR URL, `--transcribe` extracts a 16 kHz mono WAV and runs
entirely offline. `--whisper-engine auto` prefers Faster-Whisper when its package
and the selected model directory are available, then falls back to whisper.cpp:

```bash
videoflow run interview.mp4 -o edit --transcribe --asr-language pt
videoflow run interview.mp4 -o edit --transcribe \
  --whisper-engine faster-whisper --model-size small
```

The release build bundles Faster-Whisper, CTranslate2, PyAV, and the pinned
`Systran/faster-whisper-small` model. Force the fallback or a CPU/GPU policy with:

```bash
videoflow run interview.mp4 -o edit --transcribe --whisper-engine whisper.cpp
videoflow run interview.mp4 -o edit --transcribe \
  --device cuda --compute-type float16 --whisper-vad
```

Both local engines transcribe the full WAV. Do not pass pre-sliced VAD intervals;
the adapter keeps one time origin and converts every word start with floor and
every word end with ceil.

To use another CTranslate2 model directory:

```bash
videoflow run interview.mp4 -o edit --transcribe \
  --model-size medium --faster-whisper-model ~/models/faster-whisper-medium
```

`VIDEOWFLOW_FASTER_WHISPER_MODEL` overrides the model directory. The adapter
never downloads a model. Explicit `faster-whisper` fails with the expected path
and size when the model is absent; `auto` falls back to whisper.cpp.

whisper.cpp still uses a GGML model. Use a larger one by pointing at a local file:

```bash
videoflow run interview.mp4 -o edit --transcribe \
  --whisper-engine whisper.cpp --whisper-model ~/models/ggml-small.bin
```

`VIDEOWFLOW_WHISPER_BIN` and `VIDEOWFLOW_WHISPER_MODEL` override the bundled
binary and model. An SRT and an ASR URL still take precedence.

To use a remote or local OpenAI-compatible endpoint instead, set a base URL:

```bash
export VIDEOWFLOW_ASR_BASE_URL=http://localhost:8000/v1
export VIDEOWFLOW_ASR_API_KEY=          # empty for a local server
videoflow run interview.mp4 -o edit \
  --transcribe --asr-model whisper-1 --asr-language pt
```

The endpoint must support `POST /audio/transcriptions` with
`response_format=verbose_json`.

### Transcript and retakes

SRT can drive retake culling without a speech model:

```bash
videoflow run interview.mp4 -o edit \
  --transcript interview.srt --cull-retakes
```

Without an LLM, only exact repeated text is culled. With an OpenAI-compatible
endpoint, the model proposes discards per context window and the keep-last guard
restores an illegal drop:

```bash
export VIDEOWFLOW_LLM_BASE_URL=http://localhost:11434/v1
export VIDEOWFLOW_LLM_MODEL=qwen2.5:7b-instruct
export VIDEOWFLOW_LLM_API_KEY=            # empty for local Ollama
videoflow run interview.mp4 -o edit \
  --transcript interview.srt --cull-retakes \
  --strictness balanced --retake-strategy keep_last
```

The transcript and cull decisions are written to `project_state.json`. A cloud
endpoint receives the transcript text; use a local endpoint if that is not
acceptable.

### serve

```bash
videoflow serve [--host 127.0.0.1] [--port 8765]
```

- `GET /health`
- `GET /api/v1/system` — version, data directory, allowed roots, FFmpeg paths
- `POST /api/v1/jobs` — start a portable run
- `GET /api/v1/jobs/{id}` and `GET /api/v1/jobs/{id}/events` (SSE)
- `GET /api/v1/jobs/{id}/state` returns the project state for the inspector
- `POST /api/v1/jobs/{id}/cancel`
- `GET /api/v1/jobs/{id}/artifacts/{target}` downloads a timeline artifact
- `GET /` serves the bundled rack UI; the portable run panel starts a job, shows
  live progress, and links each artifact for download
- `/mcp/` is the Streamable HTTP MCP endpoint; `/mcp` returns a 307 redirect
- The default bind is loopback. Do not expose it.

Example:

```bash
curl -s -X POST http://127.0.0.1:8765/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"source":"/media/interview.mp4","output":"/projects/interview-edit"}'
```

The job starts in the background. Poll `GET /api/v1/jobs/{id}` or read the SSE
stream. `VIDEOWFLOW_ALLOWED_ROOTS` limits which paths the API and MCP accept.

### mcp

```bash
videoflow mcp
```

Speaks MCP over stdin/stdout. Register it in the host:

```json
{
  "mcpServers": {
    "videoflow": {
      "command": "C:\\Tools\\VideoFlow\\videoflow.exe",
      "args": ["mcp"]
    }
  }
}
```

Twelve tools and four resources are registered, and all of them are live.
`videoflow_load_media`, `videoflow_run_vad`, `videoflow_transcribe`,
`videoflow_get_transcript`, and `videoflow_generate_shorts` do immediate work.
Retake, zoom, and J-cut tools stage edits for the next
`videoflow_run_pipeline`; `videoflow_export_fcpxml` exports the latest completed
job. See [the MCP manual](../mcp.md) for the full contract.

### doctor

Checks:

- FFmpeg and FFprobe resolve (bundled, next to the executable, or on `PATH`)
- the Silero model and ONNX Runtime are available (optional, reported)
- Faster-Whisper, CTranslate2, and the selected small model are available
  (optional, reported)
- `VIDEOWFLOW_HOME` is writable
- UI assets are present
- the MCP SDK imports

Exit code is `0` only when every required check passes. The Silero and
Faster-Whisper entries report `found: false` without failing `doctor`, because
`auto` can fall back to FFmpeg and whisper.cpp respectively.

### demo

Creates a 6 s test clip with two silent gaps, then runs `run` on it. This is the
portable self-test. It proves FFmpeg, the timeline builder, and all three
exporters in one command.

## 5. Data and secrets

Portable mode stores data next to the executable:

```
videoflow-data/
  presets/        # user presets
  secrets.env     # optional, mode 0600 on POSIX
  .write-test
```

- Override with `VIDEOWFLOW_HOME`.
- The secret name is still `VIDEOWFLOW_LLM_API_KEY`.
- A project's own `.videoflow/` directory is not used by `run`; `run` writes the
  portable project layout shown above.

## 6. FFmpeg bundling and licensing

`scripts/build_portable.py --fetch-ffmpeg` downloads the BtbN GPL builds, copies
`ffmpeg` and `ffprobe` into `vendor/`, and PyInstaller packs them. At runtime
`find_binary` looks in the bundle before `PATH`.

- Use `--with-ffmpeg` instead to copy the FFmpeg already installed on the build
  machine. That copy may depend on the host's shared libraries.
- Builds without either flag still work if FFmpeg is next to the executable or
  on `PATH`.
- Bundled FFmpeg builds are usually GPL. Distributing the binary does not change
  FFmpeg's license. Include the FFmpeg license and source offer required by the
  build you ship. If that is not acceptable, ship without `--with-ffmpeg`.
- The project itself still has no chosen license; see `CHANGELOG.md`.

## 7. Building

```bash
# once
uv sync --extra dev --extra faster-whisper
cd ui && npm ci && npm run build && cd ..

# Linux
uv run python scripts/build_portable.py --fetch-ffmpeg --with-whisper \
  --with-silero --with-faster-whisper
./dist/videoflow version

# Windows (PowerShell)
uv run python scripts/build_portable.py --fetch-ffmpeg --with-whisper `
  --with-silero --with-faster-whisper
.\\dist\\videoflow.exe version
```

Build on the target OS. A Linux binary built on a newer glibc will not start on
an older distribution. The BtbN FFmpeg build is statically linked except for
glibc core libraries (`libc`, `libm`, `libdl`, `libpthread`), so it runs on any
distribution with a compatible glibc. The bundled `whisper-cli` is built with
static libstdc++/libgcc and OpenMP disabled, so it only needs glibc too.

### Whisper bundling and licensing

`--with-whisper` runs `scripts/fetch_whisper.py`:

- Linux: downloads whisper.cpp v1.7.6 source, builds a static `whisper-cli`, and
  copies it to `vendor/whisper/`.
- Windows: downloads the official v1.7.6 x64 zip and copies `whisper-cli.exe`,
  `whisper.dll`, and the `ggml*.dll` files.
- Both: downloads `ggml-tiny.bin` (~75 MB) from the whisper.cpp model repo.

PyInstaller places these files under `whisper/` inside the onefile bundle.
`find_whisper_binary` and `find_whisper_model` look there first, then honour
`VIDEOWFLOW_WHISPER_BIN` and `VIDEOWFLOW_WHISPER_MODEL`. The model and CLI add
roughly 80 MB to each artifact.

whisper.cpp is MIT-licensed; the Whisper model weights are distributed by
OpenAI/ggerganov under MIT terms. Review the upstream notices and include them
with any redistribution. To ship a lean build without local transcription, omit
`--with-whisper`; SRT and ASR HTTP still work.

### Faster-Whisper bundling

`--with-faster-whisper` requires `faster-whisper`, `ctranslate2`, `tokenizers`,
`av`, and `huggingface_hub` in the build interpreter. Run
`uv sync --extra faster-whisper` first. The extra pins Faster-Whisper 1.2.1 and
PyAV `<19`; PyAV 19 removed the `metadata_errors` argument used by 1.2.1.

The build script runs `scripts/fetch_faster_whisper.py`, which downloads the
pinned `Systran/faster-whisper-small` revision
`536b0662742c02347bc0e980a01041f333bce120` and verifies every SHA-256. PyInstaller
places the model under `faster-whisper/small/` and collects the CTranslate2,
Tokenizers, PyAV, and Hugging Face Hub native libraries. The model adds roughly
484 MB to each artifact; the runtime libraries add roughly 50 MB.

`--refresh-faster-whisper` re-downloads and re-verifies the model. To ship a
lean build without local Faster-Whisper, omit `--with-faster-whisper`; `auto`
then uses whisper.cpp, and SRT/ASR HTTP still work.

Faster-Whisper is MIT-licensed; CTranslate2 is MIT-licensed; PyAV is
BSD-3-Clause; the model weights are distributed by Systran under the upstream
Whisper model terms. Review and include the upstream notices with any
redistribution.

### Silero bundling

`--with-silero` requires `onnxruntime` in the build environment. The build script
downloads the pinned v5.1.2 model from
`scripts/fetch_silero.py`, verifies SHA-256
`2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f`, and
PyInstaller places it under `silero/` inside the bundle. ONNX Runtime is packed
with its native provider.

`find_silero_model` looks in the bundle, then next to the executable, and honours
`VIDEOWFLOW_SILERO_MODEL`. The model is ~2.3 MB; ONNX Runtime adds roughly 20 MB.
Silero inference is CPU-only in 0.19 and uses 16 kHz mono PCM in 512-sample
windows. Without the model or runtime, `auto` uses FFmpeg; `silero` fails with a
typed install hint.

### Linux AppImage

```bash
uv run python scripts/build_appimage.py
./dist/VideoFlow-0.21.2-x86_64.AppImage version
```

The AppImage wraps the same onefile binary. Opening it with no arguments starts
the local server and opens `http://127.0.0.1:8765/` in the browser. Passing a
command still works (`version`, `doctor`, `run`, `mcp`).

If FUSE is unavailable, run it with `--appimage-extract-and-run` or set
`APPIMAGE_EXTRACT_AND_RUN=1`. Data is stored in `videoflow-data` next to the
AppImage unless `VIDEOWFLOW_HOME` overrides it.

### Windows PE under Wine

```bash
# once: portable Wine + embeddable Python + Windows wheels
/tmp/opencode/wine/wine-11.20-amd64-wow64/bin/wine --version
/tmp/opencode/winpy/python.exe -m pip install fastapi uvicorn pydantic mcp httpx opentimelineio pyinstaller onnxruntime

VIDEOWFLOW_VENDOR_DIR='Z:\path\to\vendor-win' \
  /tmp/opencode/wine/wine-11.20-amd64-wow64/bin/wine \
  /tmp/opencode/winpy/python.exe -m PyInstaller --noconfirm --clean packaging\\videoflow.spec
```

The result is a standard PE32+ `.exe`. It was validated under Wine with
`version`, `doctor`, and `demo`, producing all three exports. Native Windows
testing is still recommended before wide distribution.

## 8. Verification checklist

- [ ] `videoflow version` prints the expected version.
- [ ] `videoflow doctor` exits 0 with FFmpeg paths inside the bundle.
- [ ] `videoflow demo -o tmp` writes three artifacts.
- [ ] `videoflow run INPUT -o tmp --transcribe` writes a transcript from the
      bundled tiny model.
- [ ] `videoflow doctor` reports the bundled whisper binary and model.
- [ ] `videoflow doctor` reports the bundled Silero model and ONNX Runtime.
- [ ] A real `videoflow run` reports `"vad_engine": "silero"` on a speech clip.
- [ ] The artifacts parse (XML/MLT) and open in the three NLEs.
- [ ] `videoflow serve` answers `/health`, `/`, and `/mcp/`.
- [ ] An MCP host lists seventeen tools over `videoflow mcp`.
- [ ] The plain binary runs with `PATH` empty, proving bundled FFmpeg is used.
- [ ] The AppImage runs `version` and `demo` (normal PATH for FUSE).
- [ ] The Windows `.exe` runs `version`, `doctor`, and `demo` (natively or under
      Wine).
- [ ] On Windows, the artifact is unblocked and SmartScreen is documented.

## 9. Limitations

- The AppImage needs FUSE or `--appimage-extract-and-run`. Without FUSE, a
  double-click cannot mount it; use the plain Linux binary or the extract flag.
- If the browser does not open, the server is still running at
  `http://127.0.0.1:8765/`; open it manually.
- The Windows PE is built with Wine and validated under Wine. Run it on a real
  Windows machine before signing or wide distribution.
- No code signing. SmartScreen will warn until a certificate is configured.
- The rack UI drives the portable run. Persistent projects and operator presets
  are available through the REST API; per-block reruns are a later pass.
- Built-in transcription is the bundled tiny model; larger models improve
  quality but are not shipped. Audio fades are written to all three NLE
  artifacts; keyframed progressive zooms remain future work.
