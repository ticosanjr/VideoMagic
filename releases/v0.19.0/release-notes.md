# VideoFlow 0.19.0

Local Faster-Whisper quality transcription, with whisper.cpp and ASR HTTP still
available as offline fallbacks.

## Highlights

- Faster-Whisper 1.2.1 runs through CTranslate2 on the CPU. The adapter sends
  the full 16 kHz WAV to the engine, requires word timestamps, and converts
  word seconds to source samples with exact floor/ceil arithmetic.
- `whisper_engine` is typed as `auto`, `faster-whisper`, or `whisper.cpp`.
  `auto` selects Faster-Whisper only when the optional package and selected
  local model are present, then falls back to whisper.cpp. An explicit engine
  fails with an actionable hint instead of silently downgrading.
- SRT and project transcripts still win. An ASR base URL still takes precedence
  over both local engines. Transcript sources are reported as
  `faster-whisper`, `whisper`, `asr`, `srt`, or `project`.
- The CLI, job API, project config, MCP `videoflow_transcribe`, and rack UI
  expose the engine, model size, device, compute type, internal VAD filter, and
  local model directory.
- `scripts/fetch_faster_whisper.py` pins the
  `Systran/faster-whisper-small` revision
  `536b0662742c02347bc0e980a01041f333bce120` and verifies every file size and
  SHA-256. The application never downloads a model implicitly.
- Release builds bundle Faster-Whisper, CTranslate2, Tokenizers, PyAV, Hugging
  Face Hub, and the ~484 MB small CTranslate2 model under `faster-whisper/small`.
  A build without `--with-faster-whisper` keeps the whisper.cpp fallback.
- `doctor` reports the Faster-Whisper package version, resolved model, and
  readiness alongside Silero, whisper.cpp, FFmpeg, the UI, and MCP.

## Artifacts

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `videoflow-0.19.0-linux-x86_64` | 817.6 MB | `60def35dd9e27a70b4a813b831c518dc060e04322d809b7fef800a5b6af13dd0` |
| `VideoFlow-0.19.0-x86_64.AppImage` | 817.2 MB | `aada128282664632647d13ff54ae87d3ab1526ae2f9acff6a4e63aef19598287` |
| `videoflow-0.19.0-windows-x86_64.exe` | 757.6 MB | `d66fa4faf80c1bed113f5513077c0e8e25035c0f7b7f8e86dbc83f8910e63fdf` |

The binaries stay beside these notes locally and are ignored by git. They were
not uploaded to GitHub.

## Run

Linux plain binary:

```bash
./videoflow-0.19.0-linux-x86_64 version
./videoflow-0.19.0-linux-x86_64 doctor
./videoflow-0.19.0-linux-x86_64 demo -o demo
./videoflow-0.19.0-linux-x86_64 run input.mp4 -o project \
  --transcribe --whisper-engine auto --asr-language en
./videoflow-0.19.0-linux-x86_64 serve
```

Linux AppImage:

```bash
chmod +x VideoFlow-0.19.0-x86_64.AppImage
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.19.0-x86_64.AppImage version
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.19.0-x86_64.AppImage doctor
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.19.0-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\videoflow-0.19.0-windows-x86_64.exe version
.\videoflow-0.19.0-windows-x86_64.exe doctor
.\videoflow-0.19.0-windows-x86_64.exe demo -o demo
.\videoflow-0.19.0-windows-x86_64.exe run input.mp4 -o project `
  --transcribe --whisper-engine auto --asr-language en
```

Use `--whisper-engine faster-whisper` to require the quality path,
`--whisper-engine whisper.cpp` to force the fallback, or `--model-size` and
`--faster-whisper-model` to select another local CTranslate2 model. Other model
sizes are not bundled; populate a model directory and point at it explicitly.
CUDA requires the CTranslate2 CUDA build and a working driver; the default is
CPU with `int8`.

## Verification

- Tests: 301 passed, 11 strict xfail, 7 deselected; coverage 99.27%; ruff and
  mypy clean; UI `check` reported 0 errors and 0 warnings, 8 Vitest tests
  passed, and the production UI build passed.
- Linux binary: `version` and `doctor` pass with bundled FFmpeg, whisper.cpp,
  the UI, MCP, Silero/ONNX Runtime 1.31.0, and Faster-Whisper 1.2.1 plus the
  bundled model. `demo` produced all three exports.
- Linux binary quality path: a real 48 kHz source with `--whisper-engine auto`
  and explicit `faster-whisper` reported `transcript_source=faster-whisper`,
  2 sentences, 14 word timings, and source-sample spans at 48 kHz. An explicit
  whisper.cpp run still completed.
- Frozen Linux API: `POST /api/v1/jobs` with `whisper_engine=faster-whisper`
  completed with `transcript_source=faster-whisper`, 2 sentences, and 14 words.
- AppImage smoke exercised `version`, `doctor`, `demo`, extract-and-run, and a
  real `serve` process answering `/health`. A real 48 kHz Faster-Whisper run
  through the AppImage also produced 2 sentences and 14 word timings.
- Windows PE under Wine: `version` and `doctor` pass with bundled FFmpeg,
  whisper.cpp, the UI, MCP, Silero, Faster-Whisper 1.2.1, and the model.
  `demo` produced all three exports. `auto` selected Faster-Whisper for a real
  48 kHz source (2 sentences, 14 words), and an explicit whisper.cpp run still
  completed.

## Caveats

- The Windows PE was built and validated under Wine, not on a native Windows
  host. Run a native smoke test before wide distribution.
- Faster-Whisper is CPU-first. GPU use requires the CTranslate2 CUDA build and
  an appropriate compute type; explicit CUDA failures do not fall back.
- Release builds bundle only the small CTranslate2 model. `tiny`, `base`,
  `medium`, and `large-v3` require a local model directory.
- The artifacts are substantially larger than 0.18.0 because they carry the
  small model and the inference runtime.
- whisper.cpp remains sentence-level in this release and may return an empty
  `words` list; Faster-Whisper is the word-level quality path.
- Per-module reruns still return typed `501 not_implemented`; run the full
  project pipeline instead.
- The Windows binary is unsigned. SmartScreen will warn until a certificate is
  configured.

See `CHANGELOG.md` for the full change list.
