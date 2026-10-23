# VideoFlow 0.51.0

This is the final release in the 0.49–0.51 sequence.

## Per-step logs

- Every recipe node has a Logs action.
- The modal loads log lines for that step from the current job.
- Log levels are color-coded; no log history is fabricated when the step has not
  run.

## Build correctness

- The UI build guard from 0.49 rebuilds the Svelte UI and rejects a stale bundle.
- The 0.48 local release was rebuilt and republished with the correct UI version.

## Validation

- 452 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 12 Playwright tests passed.

## Notes

- Kdenlive exact cross-dissolve and manual NLE QA remain pending.
- pyannote/Pexels still require real model/API credentials for final validation.
- Distribution, signing, onedir, and macOS remain out of scope.
