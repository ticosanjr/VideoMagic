# VideoFlow 0.20.0

A local file browser and a cleaner rack setup. Pick source, output, transcript,
and model paths without typing them, and see media details before running.

## Highlights

- Source, output, SRT, and model selection now use an allowlisted local
  filesystem browser. Nothing is uploaded and the video is never copied.
- The picker supports quick roots, breadcrumbs, search, extension filters,
  hidden-file control, writable checks, and folder creation. It traps focus,
  closes with Escape, and reports typed errors.
- Selecting a source probes it with FFprobe and shows duration, resolution,
  frame rate, audio rate, and size. The output project is suggested as
  `<source-stem>-videoflow`.
- The setup card is organized as numbered source/output/transcript steps, with
  YouTube/Lecture/Shorts starting points, a collapsed advanced section, inline
  validation, toasts, and a primary action that stays disabled until the run is
  valid.
- The backend adds `GET /api/v1/fs/roots`, `GET /api/v1/fs/list`,
  `POST /api/v1/fs/mkdir`, and `GET /api/v1/media/probe`. All paths use the same
  `VIDEOWFLOW_ALLOWED_ROOTS` jail as jobs; symlinks that escape a root are
  omitted or rejected.
- The existing Faster-Whisper, whisper.cpp, ASR, SRT, VAD, timeline, shorts,
  export, project, MCP, and API behavior is unchanged.

## Artifacts

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `videoflow-0.20.0-linux-x86_64` | 817.6 MB | `d90417eaa7038745fb6558832272c2a14c5aa14cf4bd0c2d00c022d8c0ab24d3` |
| `VideoFlow-0.20.0-x86_64.AppImage` | 817.2 MB | `72427ada0be6b80459bb4fb456ada6b2beb723119533b78d339e96a5ac9d6813` |
| `videoflow-0.20.0-windows-x86_64.exe` | 757.6 MB | `2e3c67805837d00e040635b5fa515eea9c4e879d25ca071ab423700a6982abe8` |

The binaries stay beside these notes locally and are ignored by git. They were
not uploaded to GitHub.

## Run

Linux plain binary:

```bash
./videoflow-0.20.0-linux-x86_64 version
./videoflow-0.20.0-linux-x86_64 doctor
./videoflow-0.20.0-linux-x86_64 demo -o demo
./videoflow-0.20.0-linux-x86_64 serve
```

Linux AppImage:

```bash
chmod +x VideoFlow-0.20.0-x86_64.AppImage
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.20.0-x86_64.AppImage version
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.20.0-x86_64.AppImage doctor
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.20.0-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\videoflow-0.20.0-windows-x86_64.exe version
.\videoflow-0.20.0-windows-x86_64.exe doctor
.\videoflow-0.20.0-windows-x86_64.exe demo -o demo
.\videoflow-0.20.0-windows-x86_64.exe serve
```

Open `http://127.0.0.1:8765/` after `serve`. The picker shows the roots from
`VIDEOWFLOW_ALLOWED_ROOTS`; add another location there if needed. The server
browses its own filesystem, which is correct for this local-only app. Set
`VIDEOWFLOW_ALLOWED_ROOTS` before starting the process.

## Verification

- Tests: 309 passed, 11 strict xfail, 7 deselected; coverage 99.28%; ruff and
  mypy clean.
- UI: `check` reported 0 errors and 0 warnings, 13 Vitest tests passed, and the
  production build passed.
- Linux binary: `version` and `doctor` pass with bundled FFmpeg, whisper.cpp,
  the UI, MCP, Silero/ONNX Runtime 1.31.0, and Faster-Whisper 1.2.1 plus the
  bundled model. `demo` produced all three exports.
- Frozen Linux UI: selected a real 48 kHz MP4, showed `0:11`, `640×360`,
  `30 fps`, `48.0 kHz`, and the file size, created an output folder, ran the
  pipeline, and wrote all three exports with `run.json` version `0.20.0`.
- AppImage smoke exercised `version`, `doctor`, `demo`, extract-and-run, and a
  real `serve` process answering `/health`.
- Windows PE under Wine: `version`, `doctor`, and `demo` pass. A served instance
  answered `/health` and returned allowlisted entries from `/api/v1/fs/roots`
  and `/api/v1/fs/list`. A real `auto` transcription produced
  `transcript_source=faster-whisper`, 2 sentences, 14 word timings, and 48 kHz
  source spans.

## Caveats

- The Windows PE was built and validated under Wine, not on a native Windows
  host. Run a native smoke test before wide distribution.
- The Windows binary is unsigned. SmartScreen will warn until a certificate is
  configured.
- The filesystem picker reads the machine running the server. A browser on
  another machine sees that server's files, not its own. Do not expose the port.
- Adding a location outside the configured roots requires an operator change to
  `VIDEOWFLOW_ALLOWED_ROOTS`; the UI does not widen the jail.
- The bundled model is the Faster-Whisper `small` CTranslate2 model. Other sizes
  require a local model directory; CUDA requires the CTranslate2 CUDA build.
- whisper.cpp remains sentence-level and may return an empty `words` list;
  Faster-Whisper is the word-level quality path.
- Per-module reruns still return typed `501 not_implemented`; run the full
  project pipeline instead.

See `CHANGELOG.md` for the full change list.
