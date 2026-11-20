# VideoFlow 3.9.2

Final worker/UI polish and release cleanup.

## Artifacts

- `videoflow-3.9.2-linux-x86_64`
- `VideoFlow-3.9.2-x86_64.AppImage`
- `VideoFlow-3.9.2-linux-x86_64.tar.zst`
- `sbom.json`, `SHA256SUMS`, `manifest.json`

## Changes

- Worker health/dashboard use compact job summaries; detailed params stay on
  `/jobs/{id}`.
- Built-in formats are read-only in the UI; duplicate to customize.
- Platforms/export targets editable in Formats.
- Correct LAN URL listing on Windows status.
- Searchable help, tooltips, and i18n updates.
- MCP: 35 tools, 16 resources.

## Verification

- MCP: 423 passed, 84% coverage.
- Python non-media: 2,835 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- UI: 52 Vitest, svelte-check 0, build OK.
- AppImage/onefile report `videoflow 3.9.2 (linux-x86_64)`.

## Windows worker

Use the 3.9.2 kit and run Install/repair. Dashboard:
`http://127.0.0.1:8766/` or menu option 12.
