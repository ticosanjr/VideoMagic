# VideoFlow 0.53.0

This release fixes the Models, Services, and Providers pages.

## Models

- Grouped by capability: ASR, diarization, and future groups.
- Shows used-by recipe steps, license, source, installed size, and path.
- Downloads are explicit and no longer gated by the external-provider toggle.
- Compact rows instead of generic cards.

## Services

- Doctor/diagnostics panel with FFmpeg, home, cache, disk, models, and UI.
- Destructive actions ask for confirmation.
- Server log and process cleanup remain available.

## Providers

- Policy stays at the top.
- Capability catalog is collapsed by default.
- Search and status filters.
- API/MCP details are behind a disclosure.
- Status summary for available/partial/planned/blocked.

## Validation

- 456 Python tests passed.
- 8 media tests passed.
- 14 Vitest tests passed.
- 14 Playwright tests passed.

## Notes

- Provider connection testing and per-provider forms remain pending.
- Distribution remains out of scope.
