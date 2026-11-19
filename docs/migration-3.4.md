# Migration to 3.4.0

3.4.0 adds optional GPU offload and the Windows worker setup. Existing projects
and settings keep working; there is no project-state schema migration.

## Settings

`settings.json` gains a `gpu` object:

```json
{
  "gpu": {
    "mode": "auto",
    "worker_url": "",
    "worker_id": "",
    "worker_token_secret": "VF_GPU_WORKER_TOKEN",
    "capabilities": {"asr": true, "render_nvenc": true},
    "shared_mount_enabled": false,
    "shared_linux_path": "",
    "shared_windows_path": "",
    "max_vram_mb": 10240,
    "model_unload_ttl_sec": 300,
    "fallback_local": true,
    "discovery_enabled": true
  }
}
```

The worker token is stored in the keyring or the 0600 fallback, not in this
file.

## API and CLI

New routes:

```text
GET   /api/v1/gpu/status
GET   /api/v1/gpu/discovery
GET   /api/v1/gpu/workers
POST  /api/v1/gpu/connect
POST  /api/v1/gpu/disconnect
PATCH /api/v1/gpu/settings
POST  /api/v1/gpu/unload
POST  /api/v1/gpu/shared/validate
POST  /api/v1/gpu/benchmark
POST  /api/v1/gpu-worker/package
GET   /api/v1/gpu-worker/package/info
```

New CLI command:

```bash
videoflow export-win-worker --output dist/
```

`VF_COMPUTE_MODE=local_only` remains a hard local-only switch. No existing
recipe changes require a new step.

## UI

Setup gains **GPU acceleration**. The header pill reflects ready, busy, local,
and offline states. Existing settings still load; the new fields use defaults.

## Release gate

A generated Windows kit is personal because it contains a pairing token. Do not
attach it to a public release. The 3.4.0 release also requires physical GPU
measurements; simulated tests alone do not satisfy the gate.
