# Performance acceptance — 3.4.0 GPU offload

Status: **blocked on physical Windows/NVIDIA hardware**.

The router, worker handlers, VRAM budget, shared mount, discovery, kit, API,
and UI are implemented and covered by automated tests. A release of 3.4.0 must
not claim the speed thresholds until `scripts/gpu_acceptance.py` runs on the
reference Windows machine.

## Required measurements

| Check | Media | Target |
| --- | --- | --- |
| ASR | 25 min audio, `large-v3-turbo`, float16 | < 45 s |
| NVENC | 11 min 1080p30 base | < 4 min |
| Matte | 3 s clip | < 5 s |
| Discovery | UDP beacon on the LAN | < 2 s |
| Failover | kill worker during 5 Shorts | detected < 3 s; remaining local |

## Command

```bash
uv run python scripts/gpu_acceptance.py \
  --worker-url http://192.168.1.45:8766 \
  --token "$VF_GPU_WORKER_TOKEN" \
  --asr-audio samples/25min.wav \
  --nvenc-video samples/11min.mp4 \
  --matte-input samples/matte-3s.mp4 \
  --discover \
  --json-out docs/qa-evidence/3.4.0-gpu.json \
  --markdown-out docs/performance-3.4.md
```

The script exits `0` only when all three media checks pass. Missing media or an
unreachable worker returns `blocked`; a measured miss returns `failed`.

## Simulated evidence

The automated suite covers:

- router health/circuit and `execute_batch` fallback after two remote items;
- UDP discovery against a real localhost socket;
- shared-output writes and traversal rejection;
- worker VRAM eviction and model unload;
- Windows kit contents and bootstrap commands;
- GPU settings, status, pairing, benchmark, and package routes;
- the Setup panel and status pill in Vitest and Playwright.

These prove the code paths, not the Windows driver/CUDA/NVENC speed.
