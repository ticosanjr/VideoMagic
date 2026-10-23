# VideoFlow 0.80.0 beta

0.80.0 is the local-first beta. Distribution, signing, macOS packaging, and
onedir builds remain out of scope.

## Timeline

- Shift-click multi-select with atomic batch moves, deletes, and ripple deletes.
- Ripple trim.
- Markers with labels and jump-to-time.
- Per-track mute/solo/lock.
- Real clip thumbnails from the source.
- Background MP4 render queue with progress, cancel, and download.
- Caption edits share timeline undo/redo.
- B-roll approval undo/redo.

## Automation

- SQLite-backed schedules with a one-time migration from JSON.
- Retry/backoff, bounded run history, and watch-file size/mtime signatures.
- Secret store: environment, OS keyring, or 0600 fallback with presence-only API.
- Provider failover for LLM chains; ASR/TTS/vision use configured providers.
- MCP tools for timeline edit, B-roll approval, providers, schedules, and review.

## Content and delivery

- `transcript.translate` writes translated JSON and SRT.
- Review comment threads and thumbnail impression/click/CTR metrics.
- `audio.qa` reports EBU R128 integrated loudness and true peak.
- NLE exports package sidecars for titles, LUT/eq, audio master, B-roll, and
  markers.

## Validation

- 464 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

## Notes

- Manual NLE QA and per-clip waveform rendering remain future work.
- The beta is local-first and loopback-only.
