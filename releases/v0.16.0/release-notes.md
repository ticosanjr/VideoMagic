# VideoFlow 0.16.0

Portable video pre-edit pipeline with offline whisper.cpp transcription and a
fully live MCP surface.

## Highlights

- All twelve MCP tools execute real work.
- All four MCP resources return live project state, transcript SRT, presets, and
  export paths.
- Granular retake, zoom, and J-cut edits stage configuration for the next
  pipeline run.
- Local transcription stages its SRT, so the pipeline uses the exact transcript
  an agent inspected.
- Shorts proposals respect retake cuts.
- Export writes Resolve FCPXML, Premiere xmeml, or Kdenlive OTIO from the latest
  completed timeline and warns when staged edits are pending.

## Artifacts

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `videoflow-0.16.0-linux-x86_64` | 239.8 MB | `1d46f10c3a978742efbd675901cf52c28a7daee738c98396444afdec695ad8ce` |
| `VideoFlow-0.16.0-x86_64.AppImage` | 240.0 MB | `20c5ca2950f45200402da29f6a0c519e1274e2cb6e3f2299cb6ddcb91baf9a32` |
| `videoflow-0.16.0-windows-x86_64.exe` | 224.0 MB | `3c5259be83ad714a2619edcd91c5641c7e07ac26a98b5700e36c9630ca481112` |

## Run

Linux plain binary:

```bash
./videoflow-0.16.0-linux-x86_64 doctor
./videoflow-0.16.0-linux-x86_64 demo -o demo
./videoflow-0.16.0-linux-x86_64 run input.mp4 -o project
./videoflow-0.16.0-linux-x86_64 mcp
```

Linux AppImage:

```bash
chmod +x VideoFlow-0.16.0-x86_64.AppImage
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.16.0-x86_64.AppImage version
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.16.0-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\videoflow-0.16.0-windows-x86_64.exe version
.\videoflow-0.16.0-windows-x86_64.exe doctor
.\videoflow-0.16.0-windows-x86_64.exe demo -o demo
```

## Verification

- Linux binary and AppImage report 0.16.0; `doctor` finds bundled FFmpeg,
  whisper, model, UI, and MCP; `demo` writes all three NLE exports.
- Frozen Linux MCP end-to-end on `jfk.mp4`: load, VAD, local transcription,
  transcript, culling, pipeline success, export, state/presets/exports
  resources.
- Windows PE under Wine reports 0.16.0; `doctor` and `demo` pass; frozen MCP
  end-to-end passes with local `whisper-cli.exe` transcription.
- Tests: 243 passed, 15 xfailed, 7 deselected; coverage 99.22%; ruff and mypy
  clean.

## Caveats

- The Windows PE was built and validated under Wine, not on a native Windows
  host. Run a native smoke test before wide distribution.
- HTTP MCP is loopback-only and has no authentication in v1; the path allowlist
  still applies.
- Artifacts are local. No GitHub release asset upload was performed.

See `CHANGELOG.md` for the full change list.
