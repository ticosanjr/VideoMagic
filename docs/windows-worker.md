# Windows GPU worker kit

The kit is a personal, self-contained bootstrap for a Windows machine with an
NVIDIA GPU. It is generated on demand because it contains a pairing token.

## Generate

```bash
uv run videoflow export-win-worker --output dist/ --shared-windows "Z:\videoflow"
```

Or use the local API:

```text
POST /api/v1/gpu-worker/package
{"token": "", "worker_id": "", "shared_windows_path": "Z:\\videoflow"}
GET  /api/v1/gpu-worker/package/info
```

The CLI prints metadata without the token by default. Use `--show-token` only
on a trusted terminal. Do not publish the generated zip or attach it to a
release.

## Contents

```text
worker.env                       token, worker id, ports, VRAM, discovery
iniciar_gpu_worker.bat           installs and starts the worker
instalar_autostart_windows.bat   schtasks ONLOGON registration
parar_gpu_worker.bat             stops the worker
status_gpu_worker.bat / .ps1     prints /health or "offline"
LEIA-ME.txt                      operator instructions
worker/                          gpu-worker source fallback
wheels/                          optional prebuilt wheel
bin/                             optional ffmpeg.exe/ffprobe.exe
```

## First run

1. Extract to a short path such as `C:\VideoFlowGPU`.
2. Run `iniciar_gpu_worker.bat`.
3. The script installs `uv`, Python 3.11, a virtual environment, the worker,
   PyTorch CUDA, faster-whisper, rembg, and OpenCV.
4. It adds a private-profile firewall rule for TCP 8766 when run as
   Administrator.
5. It starts `videoflow-gpu-worker` using `worker.env`.

The first run is network-heavy and can take several minutes. Subsequent runs
reuse `.venv`.

## Pairing

On the Linux controller, open the GPU setup and connect to the Windows LAN IP
on port 8766 using the token in `worker.env`. The worker advertises itself via
UDP 8767 when `VF_GPU_DISCOVERY=1`.

## Shared mount

Set `VF_GPU_SHARED_ROOT` in `worker.env` to the Windows path of a folder that is
also mounted on Linux. Use `POST /shared/validate` or the UI validation button
before a longform NVENC render. Without a mount, the controller streams short
artifacts over HTTP.

## Security

- `worker.env` contains a secret. Keep the zip private.
- The worker is LAN-only; do not expose port 8766 to the internet.
- The firewall rule is limited to the private profile.
- The kit's `bin/` files are optional; provide a Windows NVENC FFmpeg build if
  the machine does not already have one on `PATH`.
- The public release contains only the generator and scripts, never a generated
  zip with a token.

## Autostart

Run `instalar_autostart_windows.bat` as Administrator. It registers:

```text
schtasks /SC ONLOGON /TN "VideoFlow GPU Worker" /TR "...iniciar_gpu_worker.bat --silent"
```

Remove it with:

```bat
schtasks /Delete /TN "VideoFlow GPU Worker" /F
```
