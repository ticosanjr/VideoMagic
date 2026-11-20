# VideoFlow 3.16.0

MCP delivery and worker execution fix release.

## Fixed

- MCP servers share the app's `settings.json` and `gpu.json`; they no longer
  override `VIDEOWFLOW_HOME`, so a worker connected in the UI is visible to the
  agent.
- Packaged MCP commands use a stable launcher instead of a disposable
  AppImage `/tmp/.mount_*` executable.
- Workspace install is local-only by default. Global VideoFlow entries can be
  removed explicitly and unrelated MCP servers are preserved.
- Worker ASR/matte models register in `ModelRegistry`; warmup no longer fails
  with duplicate `capability`.
- Worker runtime includes `setuptools`, fixing `pkg_resources`.
- Worker `/health` reports the real package version.
- OpenCode MCP timeout raised to 120 s startup/catalog.

## Added

- `selftest` capability and `POST /api/v1/gpu/selftest` with a
  “Test execution” button in Setup -> GPU.
- MCP health route and cleanup endpoint.
- Onedir AppImage build: no onefile extraction on every MCP launch.
  MCP initialize dropped from minutes to about 2 seconds in local testing.
- Stable Linux shell launcher and Windows `.cmd` wrapper.

## Verification

- Python non-media: 2,875 passed, 1 skipped, 1 xfailed.
- MCP: 431 passed, 84% coverage, 35 tools, 16 resources.
- Media: 29 passed, 2 skipped.
- UI: 56 Vitest, svelte-check 0, build OK.
- AppImage/onefile report `videoflow 3.16.0 (linux-x86_64)`.
- AppImage `version` ~0.6 s; MCP initialize ~2 s.

## Upgrade steps

1. Install 3.16.0.
2. Setup -> Workspace: select the project folder and install MCP locally.
3. Click “Remove global VideoFlow MCP” if the old global config exists.
4. Setup -> GPU: reconnect the worker.
5. Click “Test execution”.
6. Windows: install the 3.16.0 worker kit and run Install/repair.

Physical RTX 3060 NVENC certification still requires the Windows machine.
