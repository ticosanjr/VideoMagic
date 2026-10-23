# VideoFlow 0.67.0

0.67.0 turns VideoFlow into a recipe studio with a professional canvas
timeline. It also removes the legacy rack/project backend and moves every
persistent error to a top-of-panel banner.

## Canvas timeline

- Konva tracks for video, dialogue, captions, and B-roll.
- Ruler scrubbing, draggable playhead, zoom, fit, and hover-free editing.
- Clip drag with snapping to the playhead, clip edges, captions, and zero.
- Red trim handles on the selected clip with a live ghost.
- Toolbar: play/pause, timecode, undo, redo, split, delete, ripple delete,
  snap, fit, and zoom.
- Keyboard: Space, `S`, Delete, Shift+Delete, Ctrl/Cmd+Z,
  Ctrl/Cmd+Shift+Z.
- Synced MP4 preview and wavesurfer.js waveform; on-demand 540p proxy.
- Undo/redo persisted in `timeline_history.json`; every edit increments
  `revision` and warns that artifacts must be re-rendered.

## API

- `PATCH /api/v1/jobs/{id}/timeline` accepts `trim`, `move`, `delete`,
  `split`, and `ripple`.
- `POST /api/v1/jobs/{id}/timeline/undo` and `/redo`.
- `GET/PATCH /api/v1/jobs/{id}/broll` for approval and ordering.
- `GET/PUT/DELETE /api/v1/providers`, `POST /providers/{id}/default`, and
  `GET /providers/resolve?capability=...`.
- Background model downloads: `POST /models/{id}/download`,
  `GET /models/downloads`, `DELETE /models/downloads/{id}`.

## Content and automation

- Real `audio.master` with high-pass, FFT denoise, and EBU R128 loudness.
- Real `titles.plan` with title cards and speaker lower thirds.
- Real `analytics.import` from CSV and `review.queue` checklist.
- Multi-variant thumbnail generation.
- Executable `flow.conditional`, `flow.loop`, and `flow.subflow`.
- B-roll approval consumed by the Shorts renderer.
- Persistent provider configuration with fallback chains; the LLM runner uses
  the configured chain when no explicit base URL is set.
- Background model downloads with progress, cancellation, and checksums.

## Removed legacy

- Project/module API routes, `ProjectStore`, module registry, legacy planning
  runner, and their tests.
- Rack UI: module cards, Studio panel, project templates screen, embedded
  caption preview, and dead configuration state.
- The global run form. Recipes are the only execution path.

## Errors at the top

A shared sticky `ErrorBanner` (`role="alert"`, copy diagnostics, dismiss) is
used by the page, recipes, assets, timeline, models, services, providers,
publish, short editor, and path picker. Footer error blocks are gone.

## Validation

- 448 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 18 Playwright tests passed.

## Notes

- Distribution, signing, macOS packaging, and onedir builds remain out of
  scope.
- Face reframing, color/LUT, multicam, and manual NLE QA remain future work.
