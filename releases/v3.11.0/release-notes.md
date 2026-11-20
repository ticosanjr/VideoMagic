# VideoFlow 3.11.0

Complete Windows GPU worker release and public tokenless kit.

## Artifacts

- `videoflow-3.11.0-linux-x86_64`
- `VideoFlow-3.11.0-x86_64.AppImage`
- `VideoFlow-3.11.0-linux-x86_64.tar.zst`
- `VideoFlow-Windows-GPU-Worker-3.11.0.zip`
- `sbom.json`, `SHA256SUMS`, `manifest.json`

## Windows worker kit

The public kit is tokenless and safe to attach to a release. It contains:

- `VideoFlowGPU.bat` and `VideoFlowGPU.ps1`;
- `videoflow_gpu_worker-3.11.0` wheel;
- offline Windows runtime wheels;
- expected version and checksums;
- installation instructions.

First run generates `worker.env` locally, starts discovery, enables LAN-open for
private networks, and updates firewall rules for all profiles. The embedded
dashboard is at `http://127.0.0.1:8766/` or menu option 12.

## P0 additions

- Public tokenless Windows kit build and release asset.
- Windows CI builds and validates the kit (no `worker.env`, wheel and dashboard
  present).
- Release workflow publishes the kit automatically.
- GPU smoke supports LAN discovery and health/overview/dashboard checks
  (`--discover`, `--skip-jobs`).
- GPU acceptance supports discovery and `--require-nvenc`.

## Verification

- MCP: 423 passed, 84% coverage, 35 tools, 16 resources.
- Python non-media: 2,838 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- UI: 52 Vitest, svelte-check 0, build OK.
- AppImage/onefile report `videoflow 3.11.0 (linux-x86_64)`.
- Public Windows kit: 3.8 MB, no token, worker wheel + dashboard verified.
- Physical RTX 3060 NVENC certification remains pending; evidence is marked
  blocked in `docs/qa-evidence/3.11.0-gpu.json`.

## Windows

Download `VideoFlow-Windows-GPU-Worker-3.11.0.zip`, extract to a short path, run
`VideoFlowGPU.bat`, choose Install/repair, then Start. Linux discovers it
automatically.
