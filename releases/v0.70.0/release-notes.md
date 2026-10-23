# VideoFlow 0.70.0

0.70.0 hardens the timeline and closes the automation, delivery, and rendering
gaps left after 0.67.0.

## Timeline hardening

- Incremental Konva rendering: the scene layer is separate from the playhead and
  guide overlay. Scrubbing no longer rebuilds every clip.
- Editable playhead timecode.
- Per-clip transition type and frame length, scale, position, and audio fade
  in/out from the inspector and API.
- Multi-entry B-roll rendering: every approved entry is overlaid in order.
- Background preview rendering with progress, cancellation, and status polling.
- Preview applies `titles.ass`, `color/filters.json`, and
  `audio/master-filters.json` to the re-rendered timeline.

## Rendering

- `titles.plan` writes ASS title cards and speaker lower thirds.
- `audio.master` writes the filter chain consumed by previews.
- New `color.grade` step with deterministic `eq` and optional `.cube` LUT.
- `export_mp4` accepts audio, video, and ASS overlay filters.
- Thumbnail A/B variants and persisted selection.

## Automation

- `flow.loop` over files isolates source, output, artifacts, warnings, and
  Shorts per item.
- Persistent once, interval, and watch-folder schedules with a local 20-second
  scheduler.
- Run-now, status, last-run, seen files, and errors.
- Provider fallbacks for LLM, ASR, TTS, and vision.
- Resumable model downloads with HTTP Range and restart-safe status.

## Review

- Review checklist approval/rejection with reviewer and comment.
- Deliverables panel in the timeline shows review checks and thumbnails.

## Validation

- 455 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

## Notes

- Distribution, signing, macOS packaging, and onedir builds remain out of
  scope.
- Manual NLE QA, multi-select dragging, and multicam switching remain future
  work.
