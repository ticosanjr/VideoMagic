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
VideoFlowGPU.bat                 single entry point; double-click for the menu
VideoFlowGPU.ps1                 install/repair, start, stop, status, doctor,
                                 logs, autostart, uninstall, supervisor
worker.env                       token, worker id, ports, VRAM, discovery
worker.env.bak                   token/backup restored during repair
expected_version.txt             worker version expected by the kit
LEIA-ME.txt                      operator instructions
worker/                          gpu-worker source fallback
wheels/                          prebuilt videoflow_gpu_worker wheel
bin/                             optional ffmpeg.exe/ffprobe.exe
logs/                            bootstrap.log and worker-error.log
```

## Single entry point

Double-click `VideoFlowGPU.bat`. The menu offers:

```text
1) Install / update / repair
2) Start worker
3) Stop worker
4) Status
5) Doctor
6) Install autostart
7) Remove autostart
8) Show logs
9) Uninstall virtual environment
0) Exit
```

Command-line actions are also accepted:

```bat
VideoFlowGPU.bat Install
VideoFlowGPU.bat Start
VideoFlowGPU.bat Stop
VideoFlowGPU.bat Status
VideoFlowGPU.bat Doctor
VideoFlowGPU.bat Repair
VideoFlowGPU.bat Autostart
VideoFlowGPU.bat --silent
```

## First run and repair

1. Extract to a short path such as `C:\VideoFlowGPU`.
2. Run `VideoFlowGPU.bat` and choose **Install / update / repair**.
3. The script installs `uv`, Python 3.11, the worker from `worker\` or the
   bundled wheel, CUDA PyTorch, faster-whisper, rembg, OpenCV, and an NVENC
   FFmpeg build when none is present.
4. It adds a private-profile firewall rule for TCP 8766 when run as
   Administrator.
5. Choose **Start worker**.

The first run is network-heavy and can take several minutes. The bootstrap is
idempotent: a broken `.venv` is rebuilt, the expected worker version is
reinstalled, missing Python packages are repaired, `worker.env` is restored
from backup when possible, and the shared-mount failure falls back to HTTP.

The supervisor restarts the worker after a crash with exponential backoff and
writes logs under `logs/`.

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

Choose **Install autostart** in `VideoFlowGPU.bat` (or run
`VideoFlowGPU.bat Autostart`). It registers an `AtLogOn` scheduled task that
runs `VideoFlowGPU.ps1 -Action Start -Silent`. Remove it from the menu or with:

```powershell
Unregister-ScheduledTask -TaskName "VideoFlow GPU Worker" -Confirm:$false
```
