# VideoFlow 0.35.0

This release focuses on diagnosis and UI testing.

## Failed-run diagnostics

- Recipe failures now write `work/failure.json` with:
  - failing stage;
  - error payload;
  - FFmpeg command when applicable;
  - stderr tail;
  - last 200 log lines.
- `IngestError` carries `command` and `stderr`, so API errors expose the failed
  FFmpeg invocation instead of only “ffmpeg failed”.
- Success, failure, and cancellation now share one history-recording path.

## Persisted failures

- `work/run-history.json` records `failed` and `cancelled` runs with their error.
- The Run history modal shows failed runs after a restart.
- Comparison still works for successful runs.

## Playwright

- Installed `@playwright/test` and Chromium.
- Added a JSON reporter at `ui/test-results/results.json`.
- E2E coverage:
  - recipe graph loads from JSON fixtures;
  - inspector transition controls update step params;
  - add-step palette adds a node;
  - persisted history shows succeeded and failed runs.

## Validation

- 427 Python tests passed.
- 14 Vitest tests passed.
- 3 Playwright E2E tests passed.
- AppImage 0.35.0 built.

## Artifacts

- `videoflow-0.35.0-linux-x86_64` — SHA-256 `3a12029d50953bbd12a53cf867ac5b17850c8dfaad3c5845bbd65adf7c2b02d3`
- `VideoFlow-0.35.0-x86_64.AppImage` — SHA-256 `fb9f0278bc53d0aada1a489895ac0a8cc8b2a7b058751a8a1c77ce1af95acb28`
