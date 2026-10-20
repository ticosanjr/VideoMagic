# Portable executable manual

VideoFlow ships as one console executable per operating system. It contains the
Python runtime, the CLI, the API, the MCP server, the rack UI, presets, and,
when built with `--with-ffmpeg`, FFmpeg and FFprobe.

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
| `videoflow doctor` | FFmpeg/FFprobe, data directory, UI assets, MCP import |
| `videoflow demo -o DIR` | Generates a 6 s fixture and runs the whole pipeline |
| `videoflow run INPUT -o DIR` | Ingest, silence detection, cuts, J/L, zooms, three NLE exports |
| `videoflow serve` | HTTP API + MCP Streamable HTTP + static rack UI |
| `videoflow mcp` | MCP over stdio for an agent host |

`run` is the model-free path: FFmpeg `silencedetect` finds speech. It does not
transcribe, cull retakes, or generate shorts yet. Those engines are specified and
still stubbed.

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
videoflow run INPUT [-o DIR] [--noise-db -30] [--min-silence-ms 400]
                    [--min-speech-ms 100] [--no-jcuts] [--l-cuts] [--no-zooms]
                    [--offset-ms 200] [--crossfade-ms 20] [--dialect 1.9]
                    [--transcript subs.srt] [--cull-retakes]
                    [--llm-base-url URL] [--llm-model MODEL]
                    [--strictness balanced] [--retake-strategy keep_last]
```

Default output is `INPUT-stem-videoflow` next to the source.

Writes:

```
DIR/
  project_state.json
  run.json
  work/source.wav
  exports/timeline.fcpxml   # Resolve
  exports/timeline.xml      # Premiere
  exports/timeline.otio     # Kdenlive
```

`run.json` is the machine-readable report: media info, speech interval count,
segment counts, transcript/retake counts, warnings, artifact paths, PCM digest,
and elapsed time.

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

If you do not have an SRT, point VideoFlow at an OpenAI-compatible transcription
endpoint (OpenAI, Groq, or a local faster-whisper server):

```bash
export VIDEOWFLOW_ASR_BASE_URL=http://localhost:8000/v1
export VIDEOWFLOW_ASR_API_KEY=          # empty for a local server
videoflow run interview.mp4 -o edit \
  --transcribe --asr-model whisper-1 --asr-language pt
```

The endpoint must support `POST /audio/transcriptions` with
`response_format=verbose_json`. An SRT still takes precedence.

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

Twelve tools and four resources are registered. Four tools are live:
`videoflow_load_media`, `videoflow_run_pipeline`, `videoflow_get_job`, and
`videoflow_cancel_job`. The neural tools return a structured
`not_implemented` result.

### doctor

Checks:

- FFmpeg and FFprobe resolve (bundled, next to the executable, or on `PATH`)
- `VIDEOWFLOW_HOME` is writable
- UI assets are present
- the MCP SDK imports

Exit code is `0` only when every required check passes.

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
uv sync --extra dev
cd ui && npm ci && npm run build && cd ..

# Linux
uv run python scripts/build_portable.py --fetch-ffmpeg
./dist/videoflow version

# Windows (PowerShell)
uv run python scripts/build_portable.py --fetch-ffmpeg
.\\dist\\videoflow.exe version
```

Build on the target OS. A Linux binary built on a newer glibc will not start on
an older distribution. The BtbN FFmpeg build is statically linked except for
glibc core libraries (`libc`, `libm`, `libdl`, `libpthread`), so it runs on any
distribution with a compatible glibc.

### Linux AppImage

```bash
uv run python scripts/build_appimage.py
./dist/VideoFlow-0.14.0-x86_64.AppImage version
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
/tmp/opencode/winpy/python.exe -m pip install fastapi uvicorn pydantic mcp httpx opentimelineio pyinstaller

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
- [ ] The artifacts parse (XML/OTIO) and open in the three NLEs.
- [ ] `videoflow serve` answers `/health`, `/`, and `/mcp/`.
- [ ] An MCP host lists twelve tools over `videoflow mcp`.
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
- The rack UI drives the portable run; per-block runs, presets persistence, and
  the transcript inspector are later passes.
- Built-in transcription, shorts, and NLE audio transitions are not in this
  build. SRT retakes are.
