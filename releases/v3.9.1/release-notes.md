# VideoFlow 3.9.1

Worker dashboard polish and connection reliability fixes.

## Artifacts

- `videoflow-3.9.1-linux-x86_64` — onefile Linux binary.
- `VideoFlow-3.9.1-x86_64.AppImage` — AppImage.
- `VideoFlow-3.9.1-linux-x86_64.tar.zst` — portable onedir bundle.
- `sbom.json`, `SHA256SUMS`, `manifest.json`.

## Fixed

- GPU panel refreshes status every 5 s, retries the saved worker URL before
  scanning, and discovers every 10 s.
- Worker dashboard excludes its own polling paths from “last request”.
- Windows env records `VF_GPU_LOG_FILE`; Open logs falls back to the folder.
- Dashboard adds a benchmark action and shows the NVENC error.
- Windows worker dashboard at `http://127.0.0.1:8766/` and menu option 12.

## Verification

- MCP: 423 passed, 84% coverage, 35 tools, 16 resources.
- Python non-media: 2,835 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- UI: 52 Vitest, svelte-check 0, build OK.
- AppImage/onefile report `videoflow 3.9.1 (linux-x86_64)`.

## Windows worker

Use the 3.9.1 kit and run Install/repair; the wheel includes the embedded
dashboard, discovery, LAN-open mode, and NVENC diagnostics.
