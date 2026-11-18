# Migration to 3.2.0

3.2.0 is a clean contract. There is no compatibility layer for 3.0/3.1 project
state, caption animation aliases, beatmap keep-lists, or overlay fractions.

## Project state

- `project_state.json` is schema **4**. Older schemas are rejected with an
  actionable error; re-import the source project.
- Overlays now use `anchor`, `margin_x`, `margin_y`, and `z`. The old
  `position_x`/`position_y` fields are gone.
- Captions use `effect` only. `animation` is gone.
- `state.json` mirrors the canonical project state after every write.

## MCP

The core surface now has **32 tools**:

```text
vf_overlay_preview  vf_layout  vf_caption_preview  vf_qa_autofix
```

`vf_shorts_batch` returns a job. Use `wait=True` or `vf_job(action="wait")`.
`needs_review` is a terminal status and means the deliverable exists but failed
a hard QA criterion.

## Timeline and beatmaps

- `apply_beatmap` accepts only `keep_ranges` and `remove_ranges` in
  `time_basis` seconds. The legacy `cuts` keep-list was removed.
- `edit.timeline` persists a 500 ms final tail guard and fades the deliverable.
- `layout.json` is written next to the delivery MP4.

## Captions

- `effect="static"` emits no karaoke tags.
- `karaoke_switch` uses `\k`, `karaoke_sweep` uses `\kf`, and `pop` uses
  `\t` plus `\k`.
- Missing word timings produce proportional timings and `effect_fallback=true`.
- `WrapStyle: 0`, single-slash override tags, and mandatory `fontsdir`.

## Shorts

- Run `shorts.tighten` before rendering. `vf_shorts_batch` does it automatically.
- Candidates below the speech-density thresholds are rejected or penalized.
- `transcript.dedupe` writes `transcript_clean.json`; raw JSON is retained.

## Delivery

- Every real MP4 passes the 1-frame/frame-count/last-sentence gate with a
  100 ms container fallback.
- Final muxes use `-t`; isolated `-shortest` is gone.
- `vf_export` runs `qa.final` and returns `needs_review` when loudness,
  collisions, captions, or word fidelity fail.
- Word fidelity unavailable is a warning; measured WER >= 3% is a hard failure.

## Verification

```bash
uv sync --extra dev --extra vision --extra faster-whisper --extra tray
uv run pytest tests/unit tests/contract
./scripts/gate_local.sh --full
```
