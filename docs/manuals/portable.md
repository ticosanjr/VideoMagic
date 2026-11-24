> **2.26 note:** the legacy `videoflow run` command was removed. Use
> `videoflow recipe run <recipe-id> <source> -o <output>`; the recipe names the
> VAD, transcript, retake, timeline, and export steps explicitly.

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
| Linux x86_64 | `VideoFlow-X.Y.Z-linux-x86_64.tar.zst` | zstd, glibc from the build host |
| Linux x86_64 | `VideoFlow-X.Y.Z-x86_64.AppImage` | FUSE, or `--appimage-extract-and-run` |
| Windows x86_64 | `videoflow-X.Y.Z-windows-x86_64.exe` | Windows 10/11 x64 |

The `tar.zst` bundle is the fast local artifact: extract it with
`tar --zstd -xf VideoFlow-X.Y.Z-linux-x86_64.tar.zst` and run
`./videoflow/videoflow doctor`. The onefile binary and AppImage remain the
complete release artifacts.

Build caches are kept between runs: `build/videoflow/`, `build/videoflow-base/`,
`dist/`, `vendor/`, and `ui/node_modules/` are not cleaned automatically.
Pass `--clean` only when dependencies or the PyInstaller spec change; use
`--refresh-runtime` to rebuild the fast bundle runtime without deleting the
other caches.


PyInstaller cannot cross-compile in the usual sense. The local release script
builds Linux and AppImage natively, while the GitHub Actions release workflow
builds Windows on `windows-latest`. The Windows job smoke-tests the executable
and uploads the onefile, the CUDA onedir zip, the worker kit, `SHA256SUMS`, and
`manifest.json`.

## 1. What the executable does

| Command | Result |
| --- | --- |
| `videoflow version` | Version and platform |
| `videoflow doctor` | FFmpeg/FFprobe, Silero, Faster-Whisper package/model, data directory, UI assets, MCP import |
| `videoflow recipe run RECIPE INPUT -o DIR` | Runs a recipe with ingest, VAD, transcription, cuts, zooms, Shorts, and NLE export |
| `videoflow serve` | HTTP API + MCP Streamable HTTP + static studio UI |
| `videoflow mcp` | MCP over stdio for an agent host |

Recipes default to `audio.vad` with Silero when the model and ONNX Runtime are
present, otherwise FFmpeg `silencedetect`. Add a `transcribe` step for offline
Faster-Whisper, with whisper.cpp as the automatic fallback, a `retakes.cull`
step for transcript-driven culling, or a `shorts.select` step for vertical
clips. The LLM retake path is optional.

## 2. Linux

```bash
chmod +x videoflow
./videoflow version
./videoflow doctor
./videoflow recipe run youtube_talking_head ~/Videos/interview.mp4 -o ./interview-edit
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
.\videoflow.exe recipe run youtube_talking_head "$env:USERPROFILE\Videos\interview.mp4" -o .\interview-edit
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

### Recipes

The legacy `videoflow run` command no longer exists. Recipes name every step
explicitly, so the same graph runs from the CLI, REST API, UI, and MCP:

```bash
videoflow recipe list
videoflow recipe show youtube_talking_head
videoflow recipe run youtube_talking_head interview.mp4 -o ./interview-edit
```

Override recipe values without editing the file:

```bash
videoflow recipe run youtube_talking_head interview.mp4 -o ./interview-edit \
  --var pacing_profile=tight --force
```

A recipe writes:

```text
DIR/
  project_state.json
  run.json
  work/source.wav
  exports/youtube_master.mp4
  exports/preview_fast.mp4
  exports/timeline.fcpxml
  exports/timeline.xml
  exports/timeline.kdenlive
```

### Decupage pacing

`vf_decupage` and the `decupage.snap` step accept `pacing_profile`:

| Profile | min silence | max pause | pad before | pad after | QA dead air |
| --- | --- | --- | --- | --- | --- |
| `tight` | 220 ms | 250 ms | 60 ms | 90 ms | 550 ms |
| `balanced` | 350 ms | 420 ms | 90 ms | 130 ms | 800 ms |
| `relaxed` | 550 ms | 700 ms | 120 ms | 170 ms | 1200 ms |

The second fuzzy pass and distant retakes run by default in
`vf_decupage(action="run_full")`. Set `second_pass=false` only for a deliberate
single-pass cut.

### Preview and final renders

`vf_export`, `export.video`, and the delivery bundle accept `mode`:

- `mode="final"` renders the delivery master at the project resolution and
  writes `youtube_master.mp4`.
- `mode="preview"` renders at a maximum of 540 px, 30 fps, with `p4`/`p1`
  NVENC or `ultrafast` x264, AAC 128k, QA off, and writes
  `preview_fast.mp4` without touching `youtube_master.mp4`.

```bash
videoflow recipe run youtube_talking_head interview.mp4 -o ./interview-edit
```

With MCP, call `vf_export(project_id="...", mode="preview")` for the fast review
and `mode="final"` for delivery. If NVENC fails after probing, the render falls
back to x264 and reports `degraded=true` with
`degraded_reason="nvenc_runtime_fallback"`.

### Shorts

Shorts are a recipe step (`shorts.select`, `shorts.render`) or a standalone
command:

```bash
videoflow shorts interview.mp4 --transcript interview.srt -o shorts-out \
  --count 3 --min-sec 30 --max-sec 60
```

Each clip is rendered at 1080x1920 with center crop and burned-in captions. Use
`--no-subtitles` to skip ASS generation and `--cull-retakes` to remove repeats
before rendering. The report is `shorts-out/shorts.json`.

### Speech-to-text

Add a `transcribe` step to the recipe. The local chain prefers Faster-Whisper
when its package and model are present, then falls back to whisper.cpp. Relevant
environment overrides:

- `VIDEOWFLOW_FASTER_WHISPER_MODEL` for a CTranslate2 model directory.
- `VIDEOWFLOW_WHISPER_BIN` and `VIDEOWFLOW_WHISPER_MODEL` for whisper.cpp.
- `VIDEOWFLOW_ASR_BASE_URL`, `VIDEOWFLOW_ASR_API_KEY`, and
  `VIDEOWFLOW_ASR_MODEL` for an OpenAI-compatible ASR endpoint.

Both local engines transcribe the full WAV. The adapter never downloads a model
by itself.

### Transcript and retakes

Add `retakes.cull` after `transcribe` (and after `speech.editorial_clean` when
semantic cleanup is enabled). Without an LLM, deterministic cleanup still removes
exact repeats, stutters, aborted starts, and distant retakes. With an
OpenAI-compatible endpoint, the model proposes discards per context window and
the unique-fact guard restores illegal drops.

### serve

```bash
videoflow serve [--host 127.0.0.1] [--port 8765]
```

- `GET /health`
- `GET /api/v1/system` — version, data directory, allowed roots, FFmpeg paths
- `POST /api/v1/recipes/run` — start a recipe run
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

Thirteen core tools and thirteen resources are registered. The MCP surface is
tools-only: use `vf://docs/steps` to discover nodes and
`vf_run` to run them. Recipes are available in the UI, CLI, and
REST API, but are intentionally not exposed through MCP. See
[the MCP manual](../mcp.md) for the full contract.

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
  --with-silero --with-faster-whisper --with-tray
./dist/videoflow version

# Windows (PowerShell)
uv run python scripts/build_portable.py --fetch-ffmpeg --with-whisper `
  --with-silero --with-faster-whisper --with-tray
.\\dist\\videoflow.exe version
```

Build on the target OS. A Linux binary built on a newer glibc will not start on
an older distribution. The BtbN FFmpeg build is statically linked except for
glibc core libraries (`libc`, `libm`, `libdl`, `libpthread`), so it runs on any
distribution with a compatible glibc. The bundled `whisper-cli` is built with
static libstdc++/libgcc and OpenMP disabled, so it only needs glibc too.

### Whisper bundling and licensing

`--with-whisper` downloads or builds whisper.cpp inline:

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

`--with-tray` requires `pystray`, `Pillow`, and `python-xlib` in the build
environment (`uv sync --extra tray`); it bundles the desktop tray icon and menu.
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
./dist/VideoFlow-2.0.0-x86_64.AppImage version
```

The AppImage wraps the same onefile binary. Opening it with no arguments starts
the local server and opens `http://127.0.0.1:8765/` in the browser. Passing a
command still works (`version`, `doctor`, `recipe`, `mcp`).

If FUSE is unavailable, run it with `--appimage-extract-and-run` or set
`APPIMAGE_EXTRACT_AND_RUN=1`. Data is stored in `videoflow-data` next to the
AppImage unless `VIDEOWFLOW_HOME` overrides it.

### Windows build

```powershell
uv sync --extra dev --group dev --extra tray --extra asr-cuda
uv run python scripts/build_portable.py --fetch-ffmpeg --with-silero --with-tray --skip-ui-build
uv run python scripts/build_portable.py --onedir --name videoflow-windows-cuda `
  --fetch-ffmpeg --with-silero --with-tray --faster-whisper-runtime --with-cuda --skip-ui-build
uv run python scripts/smoke_windows.py --exe .\dist\videoflow.exe
```

The release job runs this on `windows-latest`, packages the CUDA onedir with
`ZIP_DEFLATED` level 1, and smoke-tests the executable before upload.

## 8. Verification checklist

- [ ] `videoflow version` prints the expected version.
- [ ] `videoflow doctor` exits 0 with FFmpeg paths inside the bundle.
- [ ] `videoflow recipe run youtube_talking_head INPUT -o tmp` writes the
      timeline artifacts.
- [ ] `videoflow doctor` reports the bundled whisper binary and model.
- [ ] `videoflow doctor` reports the bundled Silero model and ONNX Runtime.
- [ ] A real recipe run reports `"vad_engine": "silero"` on a speech clip.
- [ ] The artifacts parse (XML/MLT) and open in the three NLEs.
- [ ] `videoflow serve` answers `/health`, `/`, and `/mcp/`.
- [ ] An MCP host lists the full-profile tools over `videoflow mcp --profile full`.
- [ ] The plain binary runs with `PATH` empty, proving bundled FFmpeg is used.
- [ ] The AppImage runs `version` and `doctor` (normal PATH for FUSE).
- [ ] The Windows `.exe` runs `version`, `doctor`, the UI asset check, and a synthetic job.
- [ ] On Windows, the artifact is unblocked and SmartScreen is documented.

## 9. Limitations

- The AppImage needs FUSE or `--appimage-extract-and-run`. Without FUSE, a
  double-click cannot mount it; use the plain Linux binary or the extract flag.
- If the browser does not open, the server is still running at
  `http://127.0.0.1:8765/`; open it manually.
- The Windows PE is built in CI. Run the physical GPU certification on a real
  Windows machine before signing or wide distribution.
- No code signing. SmartScreen will warn until a certificate is configured.
- The rack UI drives the portable run. Persistent projects and operator presets
  are available through the REST API; per-block reruns are a later pass.
- Built-in transcription is the bundled tiny model; larger models improve
  quality but are not shipped. Audio fades are written to all three NLE
  artifacts; keyframed progressive zooms remain future work.
