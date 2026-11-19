# Short composition plan

`short_composition_plan.json` is strict input for the dynamic Shorts renderer.
A draft can use scene ids instead of timestamps; `short.plan` resolves it and
writes the strict plan plus a report.

## Draft segment

- `seg_id`, `layout`: `FULL_FACE`, `SPLIT_BROLL`, `SPLIT_SCREEN_SAFE`,
  `SPLIT_SCREEN_FILL`.
- Anchors: either `rel_start`/`rel_end` or `start_scene_id`/`end_scene_id`.
  Mixing is allowed as long as both edges are anchored.
- `face_zoom` 1.0–1.12.
- `broll_source` for `SPLIT_BROLL`.
- `screen_focus` for screen layouts.
- Optional `sfx_on_enter`.

## Resolution

- Scene ids are converted to relative times against the plan window.
- Overlaps are rejected; gaps and leading/trailing edges are filled and
  reported as warnings.
- Segments shorter than 2.5 s are merged into a neighbour.
- The strict model then guarantees: start at 0, contiguous coverage, end at the
  plan duration, canvas 1080x1920, end padding 350 ms.
- `strict=true` fails when independent validation still reports an error.

## Scene-aware safety

- `SPLIT_BROLL` over a `PROTECT_FROM_BROLL` scene becomes `SPLIT_SCREEN_SAFE`.
- Missing or invalid B-roll falls back to `FULL_FACE` with `face_zoom=1.12`
  instead of aborting the Short.
- A split-screen crop above 2.5x upscale emits `PIP_LOW_RES_WARNING` and falls
  back to `FULL_FACE`.
- Crops use the scene-median face box with 38% headroom and a hard clamp inside
  the camera frame. `smooth_track` is opt-in and applies EMA with a 5% deadzone.

## Captions and safe zones

- Bottom safe zone is 380 px (`Y=1540..1920`).
- Right safe zone is 140 px (`X=940..1080`).
- Caption blocks are centered at 800 px max width so they never enter the right
  rail; the per-layout anchor is 1360/960/840/768.

## LLM policy

`short.plan` accepts `llm_policy="caller" | "videoflow" | "none"`:

- `caller`: writes an ID-only `llm_request.json` and waits for `plan=` or
  `plan_path=`.
- `videoflow`: calls the configured LLM client once with the
  `shorts.composition` role.
- `none`: deterministic mapping from scene layouts to safe layouts.

No policy receives absolute timestamps.

## Captions, rhythm, and ending

`short.captions` runs after plan validation:

- 3–4 words per block, max 18 characters per line, max 2 lines.
- `\an5\pos(540,Y)` with the layout anchor 1360/960/840/768.
- Blocks are split at layout boundaries; the sanitizer trims overlaps by 10 ms
  and drops blocks shorter than 60 ms.
- Layout cuts snap to a caption/ASU boundary within ±300 ms while keeping both
  segments at least 2.5 s.
- SFX cue on layout change at `start - 100 ms`, `-18 dB`, with per-segment
  `sfx_on_enter` override.
- The content end gets +350 ms, preferring the next speech edge or an RMS
  valley within ±150 ms, with an 80 ms audio fade.

## Render

`short.render` builds one filter graph per segment and writes it with
`-filter_complex_script`:

- Crop/scaled face, screen, and B-roll panels are composed with `vstack`, a
  4 px divider, and a bottom pad when the layout leaves the Shorts safe zone
  empty.
- Micro-clips are normalized to 1080x1920, target FPS, `setsar=1`,
  `yuv420p`, and 48 kHz audio.
- Segments are concatenated with the concat demuxer; ASS is burned once in the
  final pass.
- Final audio is `loudnorm=I=-14:TP=-1.5:LRA=9`, with SFX mixed at -18 dB and
  an 80 ms fade.
- NVENC uses `h264_nvenc`, VBR CQ 19, preset p5; local fallback uses
  `libx264` and records `degraded=true`.
- `compute_policy` supports `auto`, `local`, `remote`, and `remote_only`.

## FCPXML handoff

`short.export` writes a Resolve-ready timeline:

- V1: rendered Short base.
- V2: one cropped face-panel clip per render segment.
- A1: source voice segments aligned to the Short timeline.
- A2: SFX assets at their cue times.
- Captions become editable titles on lane 6; layout changes become sequence
  markers.
- `short.qa` validates the rendered 1080x1920 output, caption spans and safe
  zones, duration, and the FCPXML lanes/media.

Use `uv run python scripts/fcpxml_smoke.py <file.fcpxml>` before opening
Resolve.
