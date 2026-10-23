# VideoFlow 0.48.0

This is the final release in the 0.43–0.48 sequence.

## Canvas

- Persisted viewport pan/zoom.
- Persisted node width.
- Inline node fields, validation, pin/expand, and per-step progress from 0.43.
- Auto-layout reset.

## Preview and history

- Successful jobs can generate and play a 540p proxy.
- Persisted batch history is listed and loadable.
- Jobs, batches, and run history support `limit`/`offset` and return totals.

## Engine

- Global analysis-cache pruning by age and size.
- Preview proxy endpoint.
- `PipelineRunner` is planning-only; recipe engine owns execution.
- Model catalog includes pyannote 3.1 download.

## Validation

- 452 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 10 Playwright tests passed.
- CI and tag release workflow are green.

## Notes

- Arrays and deeply nested objects still fall back to advanced JSON.
- Kdenlive cross-dissolve and manual NLE import QA remain pending.
- pyannote/Pexels still need real credentials/model access for final validation.
- Distribution, signing, onedir, and macOS remain out of scope.
