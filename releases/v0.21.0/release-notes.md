# VideoFlow 0.21.0

Configurable zoom bounds, audio fades, Shorts selection, and karaoke caption
styling, exposed from the rack, job API, project config, presets, and MCP.

## Highlights

- **Zoom bounds:** `min_scale`, `max_scale`, and `punch_in_scale` are validated
  against the configured window. The state model accepts scales up to 4.0.
- **Audio fades:** `fade_in_ms`, `fade_out_ms`, and `fade_curve` join the
  existing crossfade and offset controls. The timeline stores per-clip fade
  lengths and the selected curve.
- **Shorts as a complement:** `videoflow run --shorts` now produces the main
  project and additional vertical MP4s in the same output. The standalone
  `videoflow shorts` command remains available for vertical-only work.
- **Shorts selection:** target count, minimum count, duration window, and
  `auto|llm|heuristic` ranking are configurable. The LLM client is created for
  Shorts even when retake culling is off. The heuristic ranks hook, impact,
  emotion, concrete numbers, contrast, and diversity instead of taking the
  first windows.
- **Karaoke captions:** font family, size, weight, italic, uppercase,
  primary/highlight/outline colors, outline width, shadow color/offset/opacity,
  background box color/opacity/padding, alignment, normalized position, max
  width, animation, and word-timing fallback are configurable.
- **ASS karaoke:** word timings become `\\k`/`\\kf` tags. Missing word timings
  fall back to proportional or sentence timing with a warning.
- **UI:** an explicit “Also render vertical shorts” control, “Main + Shorts”
  starting point, target/minimum Short inputs, color pickers, and the full
  caption style group. The setup form validates zoom windows and Shorts
  prerequisites before starting.
- **API/MCP:** the job request and MCP override surface accept the same zoom,
  fade, Shorts, and caption fields. `videoflow_generate_shorts` accepts
  `min_count` and `selection_mode`.

## Artifacts

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `videoflow-0.21.0-linux-x86_64` | 817.6 MB | `3ee6d6e240cd41e4a56c23456cf73dd5e147091987bf9a9ad9980132e838bbea` |
| `VideoFlow-0.21.0-x86_64.AppImage` | 817.2 MB | `b06fc88b4f74bfa6d0935870b3857d3ddc433f1bcd06758a48ebf9d54deafd37` |
| `videoflow-0.21.0-windows-x86_64.exe` | 757.7 MB | `e978080c440c02a148b0e4b1616e170c01dc1f6e9531a5f452577a1cc28e1ce0` |

The binaries stay beside these notes locally and are ignored by git. They were
not uploaded to GitHub.

## Run

```bash
./videoflow-0.21.0-linux-x86_64 version
./videoflow-0.21.0-linux-x86_64 doctor
./videoflow-0.21.0-linux-x86_64 run input.mp4 -o project \
  --transcript input.srt --shorts --shorts-count 3 --shorts-min-count 3
./videoflow-0.21.0-linux-x86_64 serve
```

The AppImage works with `APPIMAGE_EXTRACT_AND_RUN=1` when FUSE is unavailable.
Windows commands mirror the Linux commands.

## Verification

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- UI: 0 errors/warnings, 13 Vitest tests, production build passed.
- Linux binary: `version` 0.21.0, `doctor` ready, a real 48 kHz run with local
  transcription and `--shorts` produced the three main timeline artifacts, two
  vertical MP4s (the source only supported two), `shorts.json`, and karaoke ASS.
- Windows PE under Wine: `version` and `doctor` pass; a real run with `--shorts`
  produced the main artifacts and Shorts with karaoke ASS.
- AppImage smoke exercised `version`, `doctor`, `demo`, extract-and-run, and
  `serve`.

## Caveats

- **NLE transition elements are still pending.** Fade timing and curve are
  configured and stored in the timeline, but FCPXML/xmeml/MLT currently carry
  the audio cut offsets, not dedicated crossfade transition elements.
- **Karaoke styling is mapped to ASS.** Background box and shadow both use
  libass's back-colour layer; a simultaneous box plus separate shadow colour
  depends on libass and may not match a browser preview exactly.
- Caption preview and per-Short editors are not in this build.
- The Windows PE was validated under Wine, not native Windows, and is unsigned.
- The three NLE import flows still need a manual click-through gate in Resolve,
  Premiere, and Kdenlive.

See `CHANGELOG.md` for the full change list.
