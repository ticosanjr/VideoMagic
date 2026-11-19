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
                                 logs, autostart, benchmark, uninstall, supervisor
requirements-windows.txt         CUDA PyTorch, faster-whisper, rembg, ONNX GPU
wheels/                          worker wheel + its Python dependencies
checksums.txt                    SHA-256 for every wheel
worker.env                       token, worker id, ports, VRAM, discovery
worker.env.bak                   token/backup restored during repair
expected_version.txt             worker version expected by the kit
LEIA-ME.txt                      operator instructions
bin/                             optional ffmpeg.exe/ffprobe.exe
logs/                            bootstrap.log, install-*.log, worker-error.log
```

The worker and its Python dependencies are installed **offline** from
`wheels/`. The heavy CUDA runtime (PyTorch, CTranslate2, ONNX Runtime) is
downloaded after the worker is already installed, so a PyPI/TLS failure cannot
break the first step.

To regenerate the offline wheel set after a worker dependency change:

```bash
python3 -m pip download \
  --dest src/videoflow/templates/wheels/win \
  --only-binary=:all: \
  --platform win_amd64 \
  --python-version 3.11 \
  --implementation cp \
  --abi cp311 \
  'fastapi==0.149.0' 'uvicorn==0.54.0' 'httpx==0.28.1' \
  'pydantic==2.14.1' 'python-multipart==0.0.32'
```

## Single entry point

Double-click `VideoFlowGPU.bat`. The menu offers:

```text
1) Install / repair everything
2) Start worker
3) Stop worker
4) Status / health
5) Full diagnostic
6) Show logs
7) Install autostart
8) Remove autostart
9) Quick benchmark
10) Open logs folder
11) Uninstall venv
0) Exit
```

The menu never closes on an error. The error panel shows the code, step,
message, exact command, stderr tail, log path, and a fix hint, then returns to
the menu. Only `0) Exit` closes the window.

Command-line actions are also accepted:

```bat
VideoFlowGPU.bat Install
VideoFlowGPU.bat Repair
VideoFlowGPU.bat Start
VideoFlowGPU.bat Stop
VideoFlowGPU.bat Status
VideoFlowGPU.bat Doctor
VideoFlowGPU.bat Diagnose
VideoFlowGPU.bat Autostart
VideoFlowGPU.bat --silent
```

## First run and repair

1. Extract to a short path such as `C:\VideoFlowGPU`.
2. Run `VideoFlowGPU.bat` and choose **Install / repair everything**.
3. The script installs `uv`, a private Python 3.11, the worker from `wheels/`,
   CUDA PyTorch, faster-whisper, CTranslate2, rembg, ONNX Runtime GPU, OpenCV,
   and an NVENC FFmpeg build when none is present.
4. It adds a private/domain firewall rule for TCP 8766 and UDP 8767 when run as
   Administrator.
5. Choose **Start worker**.

The first run is network-heavy and can take several minutes. The bootstrap is
idempotent: a broken `.venv` is rebuilt, the expected worker version is
reinstalled, missing Python packages are repaired, `worker.env` is restored
from backup when possible, and a shared-mount failure falls back to HTTP.

The supervisor restarts the worker after a crash or a 15-second health timeout
with exponential backoff and writes logs under `logs/`. On Windows it assigns
the worker to a Job Object so `ffmpeg.exe` children cannot stay alive after a
cancel or exit.

## Error capture

Every native command writes stdout, stderr, exit code, and the exact command to
`logs/install-<timestamp>.log`. The last error is also written to
`logs/last-error.json`. **Diagnostic** creates a zip with the logs and the
Python/GPU environment. A Python traceback is shown in full, never truncated to
`Traceback (most recent call last):`.

## Pairing

On the Linux controller, open the GPU setup and connect to the Windows LAN IP
on port 8766 using the token in `worker.env`. The worker advertises itself via
UDP 8767 when `VF_GPU_DISCOVERY=1`.

## HTTP streaming and shared mount

HTTP is the default transport. The controller uploads inputs and downloads
artifacts in chunks, with resume and SHA-256 verification. A shared mount is
optional and only used as an accelerator.

Set `VF_GPU_SHARED_ROOT` in `worker.env` to the Windows path of a folder that is
also mounted on Linux. Use `POST /shared/validate` or the UI validation button
before a longform NVENC render. If the mount is unavailable or a write fails,
the job continues over HTTP automatically and is marked as degraded.

For CIFS mounts on Linux, use `actimeo=1` and a modern SMB dialect to reduce
stale metadata after the Windows worker writes an output.

## Security

- `worker.env` contains a secret. Keep the zip private.
- The worker is LAN-only; do not expose port 8766 to the internet.
- The firewall rule is limited to private/domain profiles.
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
