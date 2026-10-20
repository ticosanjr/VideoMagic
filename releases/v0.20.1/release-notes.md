# VideoFlow 0.20.1

Export compatibility fix for DaVinci Resolve, Adobe Premiere Pro, and Kdenlive.

## What changed

- **Resolve**: FCPXML 1.9/1.10 now writes the source URL in a
  `<media-rep kind="original-media" src="..."/>` child. The old `<asset src>`
  form is only valid for FCPXML 1.8 and could make Resolve reject or offline the
  timeline. The asset also carries `videoSources`, and clips carry
  `srcEnable="all"` and `audioRole="dialogue"`.
- **Premiere**: xmeml is now version 4 with `explodedTracks="true"`, a sequence
  UUID, `file://localhost/` path URLs (Windows drive letters as `C%3a`), a full
  `<file>` definition on every video and audio clipitem, and explicit A/V
  `<link>` groups. The Basic Motion effect id is now `basicmotion`.
- **Kdenlive**: the deliverable is now a native `timeline.kdenlive` MLT project,
  not OTIO. It contains a profile, source chain, video/audio tractors, sequence
  tractor, main bin, and final tractor. The API/MCP target key remains
  `kdenlive`; the historical `write_otio` config key controls this artifact.

## Artifacts

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `videoflow-0.20.1-linux-x86_64` | 817.6 MB | `be32d5c3145cd026d3a23492db9e18d83ffd563804d70f6043f80331e115d8e3` |
| `VideoFlow-0.20.1-x86_64.AppImage` | 817.2 MB | `aa902c907b8549d0f30c44684d9802041795bb33e218f933cdeeca737a3fc245` |
| `videoflow-0.20.1-windows-x86_64.exe` | 757.6 MB | `ff2e9d0f07b72166f4ab12658175aebb1d449bcbb74f947b2fb24bd5420281ae` |

The binaries stay beside these notes locally and are ignored by git. They were
not uploaded to GitHub.

## Run

Linux plain binary:

```bash
./videoflow-0.20.1-linux-x86_64 version
./videoflow-0.20.1-linux-x86_64 doctor
./videoflow-0.20.1-linux-x86_64 run input.mp4 -o project
./videoflow-0.20.1-linux-x86_64 serve
```

Linux AppImage:

```bash
chmod +x VideoFlow-0.20.1-x86_64.AppImage
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.20.1-x86_64.AppImage version
APPIMAGE_EXTRACT_AND_RUN=1 ./VideoFlow-0.20.1-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\videoflow-0.20.1-windows-x86_64.exe version
.\videoflow-0.20.1-windows-x86_64.exe doctor
.\videoflow-0.20.1-windows-x86_64.exe run input.mp4 -o project
.\videoflow-0.20.1-windows-x86_64.exe serve
```

The three artifacts are written to `<project>/exports/`:

- `timeline.fcpxml` — DaVinci Resolve
- `timeline.xml` — Adobe Premiere Pro (FCP 7 XML version 4)
- `timeline.kdenlive` — Kdenlive 23.04+ native MLT XML

## Verification

- Tests: 310 passed, 11 xfailed, 7 deselected; coverage 99.28%; ruff and mypy
  clean.
- UI: 0 errors/0 warnings, 13 Vitest tests, production build passed.
- Linux binary: `version` 0.20.1, `doctor` ready, a real 48 kHz run wrote all
  three artifacts. The files were parsed back as FCPXML, xmeml, and MLT XML;
  the media-rep, full xmeml file/link structure, and Kdenlive sequence tractor
  were checked.
- Windows PE under Wine: `version` and `doctor` pass; a real run wrote all three
  artifacts. FCPXML used a Windows media-rep URL, xmeml used
  `file://localhost/Z%3a/...`, and the Kdenlive chain used the Windows source
  path.
- AppImage smoke exercised `version`, `doctor`, `demo`, extract-and-run, and
  `serve`.

## Important limitation

This environment does not have Resolve, Premiere, or Kdenlive installed, so the
final import click-through remains a manual gate. The files now follow the
documented interchange shapes for each application:

- Resolve FCPXML 1.9 uses `media-rep`.
- Premiere uses xmeml v4 with full file definitions and A/V links.
- Kdenlive opens its own native `.kdenlive` MLT format.

If an import still fails, keep the artifact and the exact application version;
the next fix should be based on that file rather than another format guess.

See `CHANGELOG.md` for the full change list.
