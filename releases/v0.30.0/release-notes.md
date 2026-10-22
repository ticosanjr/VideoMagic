# VideoFlow 0.30.0

This release focuses on operations and delivery.

## Persistent run history

- Successful recipe runs append a compact record to
  `<output>/work/run-history.json`.
- `GET /api/v1/runs?output=...` exposes the history.
- The comparison modal uses this history, so previous runs survive a server
  restart.

## CI and Windows

- Added GitHub Actions CI for Python lint/tests and UI check/test/build.
- Added a `windows-latest` workflow that builds `videoflow.exe` and uploads it
  as an artifact.
- No Windows PE was built locally because this machine has no Windows/Wine
  build host; the workflow is the supported path.

## Onedir build

`scripts/build_portable.py --onedir` now builds a PyInstaller `COLLECT` bundle
instead of a onefile executable. Verified locally:

```bash
dist/videoflow/videoflow version
# videoflow 0.30.0 (linux-x86_64)
```

## Validation

- 413 Python tests passed; 14 UI tests passed.
- The onedir bundle built and returned its version.
- The 0.30.0 AppImage ran two recipe jobs and `/api/v1/runs` returned both.
- The AppImage server started without a terminal, and a second launch reused it.

## Artifacts

- `videoflow-0.30.0-linux-x86_64` — SHA-256 `5af8998698d396cf341dd58e560be9b93d9d863cfc3f3012205ad8d5ff42dac0`
- `VideoFlow-0.30.0-x86_64.AppImage` — SHA-256 `dd8c19458728e79397aadd9b7a91c1e2aeb6f64d16e1f56386251357083320c6`

The build is lean; speech weights are downloaded from the Models tab.
