# VideoFlow 3.14.0

Refactor and hardening release: one scene contract, one Short IO layer, linked
styles/formats, a richer worker dashboard, safer discovery, and worker
security/retention.

## Artifacts

- `videoflow-3.14.0-linux-x86_64`
- `VideoFlow-3.14.0-x86_64.AppImage`
- `VideoFlow-3.14.0-linux-x86_64.tar.zst`
- `VideoFlow-Windows-GPU-Worker-3.14.0.zip`
- `sbom.json`, `SHA256SUMS`, `manifest.json`

## One scene contract

- New `videoflow-scene-rules` package shared by the app and the GPU worker.
- Owns sample timestamps, layout classification, editing hints, protected
  layouts, and median rounding.
- Contract tests compare local and worker results.
- Windows kit ships the rules wheel next to the worker wheel.

## One Short artifact reader

- `short_composition/io.py` centralizes plan, manifest, supercontext, cues, and
  export report precedence.
- `short.plan`, `short.captions`, `short.validate`, `short.render`,
  `short.export`, and `short.qa` use it.

## Styles and formats

- `StyleDefinition.format_id` links a style to an output format.
- Linked formats supply aspect ratio, safe zones, and caption preset.
- Unknown format ids are rejected.
- Styles UI, REST save route, and `vf_style` accept `format_id`.

## Worker status and dashboard

- `WorkerHealth` is the canonical status contract with disk, uptime, retention,
  LAN URLs, NVENC error, warmup, current job, allowlist, and token-only fields.
- Contract test guards the TypeScript `GpuWorkerStatus` interface.
- Dashboard adds GPU/VRAM/queue history, current stage/progress, clients,
  firewall, audit decision, searchable logs, and local restart.
- Restart rebuilds threads and re-enqueues queued jobs.

## Discovery

- UDP beacon, optional mDNS `_videoflow._tcp.local.`, and active scanning.
- Real interface prefixes on Linux/Windows, multiple private subnets,
  `VF_GPU_SCAN_CIDRS`, `VF_GPU_SCAN_MAX_HOSTS`, 15-second cache, and dedupe.

## Security

- `VF_GPU_ALLOWED_CLIENTS` IP/CIDR allowlist for LAN-open.
- `VF_GPU_TOKEN_ONLY=1` requires a token on the LAN while keeping loopback.
- Auth audit ring and local-only security endpoints.
- Token rotation writes `worker.token` and takes effect immediately.

## Retention and disk

- Per-job metrics in SQLite with `/api/history`.
- Artifact garbage collection for unreferenced uploads.
- Metrics pruning and worker log rotation.
- Existing HTTP 507 disk backpressure remains.

## UI tests

- SSR component tests for Styles, Formats, Help, and GPU panels.
- 56 Vitest tests total.

## Verification

- Python non-media: 2,864 passed, 1 skipped, 1 xfailed.
- MCP: 424 passed, 84% coverage, 35 tools, 16 resources.
- Media: 29 passed, 2 skipped.
- UI: 56 Vitest, svelte-check 0, build OK.
- Public Windows kit contains the 3.14.0 worker and scene-rules wheels.

## Pending

Physical RTX 3060 NVENC certification still requires the Windows machine.
