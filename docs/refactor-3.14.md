# Refactor and hardening (3.14)

## One scene contract

`packages/scene-rules` is a dependency-free package shared by the application
and the isolated GPU worker. It owns:

- deterministic sample timestamps;
- layout classification (`TALKING_HEAD`, `SCREEN_SHARE_*`, `DUAL_CANVAS_OBS`,
  `BROLL_OR_FOOTAGE`);
- editing hints (`LONG_STATIC_SHOT`, `PROTECT_FROM_BROLL`, `SAFE_FOR_BROLL`,
  `SCENE_TYPE_SWITCH`, `LOW_SHARPNESS_WARNING`, `DUAL_CANVAS_READY`);
- protected-layout rules;
- median rounding.

`application/scene_intel/layout.py`, `visual.py`, and the worker's
`handlers_gpu.py` delegate to it. A contract test compares local and worker
results across layouts, face statistics, hints, and sampling.

The Windows kit now ships `videoflow_scene_rules-<version>` next to the worker
wheel.

## One Short artifact reader

`application/short_composition/io.py` centralizes:

- plan precedence: override file, metadata, artifact;
- manifest metadata/artifact fallback;
- supercontext fallback;
- cues precedence;
- export report precedence.

`short.plan`, `short.captions`, `short.validate`, `short.render`, `short.export`,
and `short.qa` use it, so error classes, messages, and precedence are consistent.

## Formats and styles

`StyleDefinition.format_id` links a style to a format preset. When a linked
format exists:

- `aspect_ratio` comes from the format;
- empty safe zones adopt the format's safe zones;
- an empty caption preset adopts the format's preset;
- unknown format ids are rejected by `save_style`.

The Styles UI exposes a format selector, the REST save route accepts
`format_id`, and `vf_style` accepts `format_id`.

## Status contract

`WorkerHealth` is the canonical worker status contract. It now includes disk,
uptime, retention, NVENC error, LAN URLs, warmup, current job, allowlist, and
token-only fields. A test parses `GpuWorkerStatus` from `ui/src/lib/api.ts` and
fails when the frontend drifts from the backend model.

## Worker dashboard

The embedded dashboard now shows:

- GPU, VRAM, and queue history (2 minutes);
- disk free, warmup, CPU workers, and runner queue ETA;
- current stage/progress and per-job progress;
- firewall rules, connected clients, request count, and last audit decision;
- a searchable log view;
- local-only restart that rebuilds worker threads and re-enqueues queued jobs.

## Discovery

- UDP beacon remains the primary path.
- Optional mDNS `_videoflow._tcp.local.` advertisement/discovery when
  `zeroconf` is installed.
- Active scanning uses real interface prefixes when available, supports
  multiple private subnets, `VF_GPU_SCAN_CIDRS`, `VF_GPU_SCAN_MAX_HOSTS`, a
  15-second result cache, and worker-id deduplication.
- Linux parses `ip -o -4 addr`; Windows parses PowerShell `Get-NetIPAddress`;
  the fallback is a `/24`.

## Security

- `VF_GPU_ALLOWED_CLIENTS` is a comma-separated IP/CIDR allowlist for LAN-open.
- `VF_GPU_TOKEN_ONLY=1` requires a token on the LAN while keeping the local
  dashboard available on loopback.
- Auth decisions are recorded in a bounded audit ring.
- Local-only endpoints: `GET /api/security`, `GET /api/audit`,
  `POST /api/token/rotate`, `POST /api/restart`.
- Token rotation writes `worker.token` in the worker work directory and takes
  effect immediately; the file wins over the install-time env token.

## Retention and history

- Finished jobs are cleaned at startup and hourly.
- Uploaded artifacts not referenced by any job are deleted by maintenance.
- Per-job metrics are stored in SQLite and exposed through `/api/history`.
- Metrics older than `VF_GPU_METRICS_RETENTION_HOURS` are pruned.
- `worker.log` rotates to `.1` above `VF_GPU_LOG_MAX_MB`.
- Disk backpressure remains HTTP 507 below `VF_GPU_MIN_FREE_DISK_MB`.

## UI tests

The setup panels now have SSR component tests (`StylesPanel`, `FormatsPanel`,
`HelpPanel`, `GpuPanel`) plus the existing pure-helper tests.
