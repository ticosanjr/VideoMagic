# VideoFlow 0.21.1

Audio fade transitions now reach the Premiere and Kdenlive artifacts.

## What changed

- Premiere xmeml writes single-sided `transitionitem` entries around audio
  edges, using the Cross Fade (0 dB) transition. Fade-in and fade-out durations
  come from the configured timeline fades.
- Kdenlive MLT audio entries now carry a keyframed `volume` filter. The
  `level` ramp starts/ends at -60 dB and returns to 0 dB for the body of the
  clip.
- The main timeline artifacts, Shorts, caption/karaoke style, zoom window,
  SSRT/ASR/Faster-Whisper paths, and all 0.21.0 configuration controls remain.

## Artifacts

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `videoflow-0.21.1-linux-x86_64` | 817.6 MB | `b6577730be6802816831674b397532b0f66e96d5825d7a7d1cbe4b392626a74b` |
| `VideoFlow-0.21.1-x86_64.AppImage` | 817.2 MB | `459ede8ac72c6b322c6d72bc8af9e21fd3cb1c94e8c2dfd7282bd1e97a97c9b5` |
| `videoflow-0.21.1-windows-x86_64.exe` | 757.7 MB | `d7347a132daafec4e00b1be71fc19ed45b8ef1881275c88b7d95d50759b41625` |

The binaries stay beside these notes locally and are ignored by git. They were
not uploaded to GitHub.

## Verification

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- Linux binary: 0.21.1, a real 48 kHz run produced six xmeml audio
  `transitionitem` fades and a Kdenlive `volume` keyframe ramp
  (`0=-60;1=0;66=0;67=-60`).
- Windows PE under Wine: 0.21.1 and the same xmeml/Kdenlive fade structures.
- AppImage smoke: `version`, `doctor`, `demo`, extract-and-run, and `serve`.

## Caveats

- **FCPXML/Resolve fade transitions remain pending.** The FCPXML artifact still
  carries the audio offsets, but not dedicated fade elements.
- Caption preview and per-Short editors are not in this build.
- The Windows PE was validated under Wine, not native Windows, and is unsigned.
- NLE import remains a manual click-through gate.

See `CHANGELOG.md` for the full change list.
