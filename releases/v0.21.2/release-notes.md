# VideoFlow 0.21.2

FCPXML audio fades and a live caption preview round out the 0.21 line.

## What changed

- Resolve/FCPXML now writes audio fade edges as keyframed `adjust-volume` ramps
  on each `asset-clip`. The ramp uses the clip-relative
  `param > keyframeAnimation > keyframe` form required by the FCPXML 1.9 DTD.
- FCPXML sequences use the enumerated `audioRate` label (`48k`, `44.1k`, ...).
  A generated timeline validates against the official FCPXML 1.9 DTD.
- The Shorts card includes a live 9:16 caption preview. Font, size, weight,
  italic/uppercase, primary and karaoke colors, outline, shadow, box, alignment,
  position, and animation all update from the same form values used by the run.
- The existing Premiere `transitionitem` fades and Kdenlive keyframed `volume`
  filters remain in place, so all three NLE artifacts carry audio fades.

## Artifacts

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `videoflow-0.21.2-linux-x86_64` | 817.6 MB | `b0205c5a6c258ce26e091af245237a0fa780bb1fa1b150d3a1b1b1655351a94e` |
| `VideoFlow-0.21.2-x86_64.AppImage` | 817.2 MB | `69daa6c83f65f52c757df652b2dee182ece81446de50fa70f095924734c789a7` |
| `videoflow-0.21.2-windows-x86_64.exe` | 757.7 MB | `5d1283a571bb32e413a7809238308ae6ee02eaedf6fcae6d70704dd0208d65c3` |

The binaries stay beside these notes locally and are ignored by git. They were
not uploaded to GitHub.

## Verification

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- FCPXML: Linux and Windows runs validate against the official FCPXML 1.9 DTD.
  Each faded clip carries four `adjust-volume` keyframes.
- UI: `svelte-check` reports 0 errors and 0 warnings; the production build
  succeeds with 13 Vitest tests.
- Linux binary/AppImage and Windows PE: real runs produce six xmeml fade
  transition items, a Kdenlive volume ramp, and DTD-valid FCPXML fades.
- AppImage smoke: `version`, `doctor`, `demo`, extract-and-run, and `serve`.

## Caveats

- Caption preview is an approximate HTML representation; the burned-in result
  still comes from ASS and may differ slightly in font metrics and wrapping.
- A per-Short editor is still planned.
- The Windows PE is validated under Wine, not native Windows, and is unsigned.
- NLE import remains a manual click-through gate; AC-01 stays xfail until all
  three applications are checked by hand.
