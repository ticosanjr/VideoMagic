"""Generate the Windows GPU worker kit.

The zip is a personal artifact: it contains the pairing token. It is generated
on demand and is never committed or attached to a public release.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from videoflow.runtime import portable_home

ROOT = Path(__file__).resolve().parents[3]
WORKER_ROOT = ROOT / "packages" / "gpu-worker"
KIT_DIR = "kits"


@dataclass(slots=True)
class KitResult:
    path: Path
    sha256: str
    bytes: int
    token: str
    worker_id: str
    files: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def to_dict(self, *, include_token: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": True,
            "path": str(self.path),
            "name": self.path.name,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "worker_id": self.worker_id,
            "files": list(self.files),
            "created_at": self.created_at,
            "token_included": True,
            "warning": "This zip contains a pairing token. Do not publish or share it.",
        }
        if include_token:
            payload["token"] = self.token
        return payload


def _crlf(text: str) -> bytes:
    return text.replace("\n", "\r\n").encode("utf-8")


def _env_file(
    *,
    token: str,
    worker_id: str,
    shared_windows_path: str,
) -> str:
    lines = [
        "# VideoFlow Windows GPU worker. Keep this file private.",
        f"VF_GPU_TOKEN={token}",
        "VF_GPU_HOST=0.0.0.0",
        "VF_GPU_PORT=8766",
        f"VF_GPU_WORKER_ID={worker_id}",
        "VF_GPU_MAX_VRAM_MB=10240",
        "VF_GPU_MODEL_TTL_SEC=300",
        "VF_GPU_BUILTIN_HANDLERS=1",
        "VF_GPU_DISCOVERY=1",
        "VF_GPU_ADVERTISE_PORT=8767",
    ]
    if shared_windows_path.strip():
        lines.append(f"VF_GPU_SHARED_ROOT={shared_windows_path.strip()}")
    return "\n".join(lines) + "\n"


def _start_bat() -> str:
    return """@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "SILENT=0"
if /I "%~1"=="--silent" set "SILENT=1"
if not exist "worker.env" (
  echo worker.env is missing. Download the kit again.
  if "%SILENT%"=="0" pause
  exit /b 1
)
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("worker.env") do (
  if not "%%~A"=="" set "%%A=%%B"
)
if "%VF_GPU_PORT%"=="" set "VF_GPU_PORT=8766"

where uv >nul 2>&1
if errorlevel 1 (
  echo Installing uv...
  powershell -NoP -Exec Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\\.local\\bin;%PATH%"
)
where uv >nul 2>&1
if errorlevel 1 (
  echo Could not install uv. Install it from https://astral.sh/uv and rerun.
  if "%SILENT%"=="0" pause
  exit /b 1
)

if not exist ".venv\\Scripts\\python.exe" (
  uv venv .venv --python 3.11
)
call ".venv\\Scripts\\activate.bat"
uv pip install --upgrade pip
if exist "wheels\\videoflow_gpu_worker-*.whl" (
  uv pip install wheels\\videoflow_gpu_worker-*.whl
) else (
  uv pip install worker
)
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
uv pip install faster-whisper "rembg[gpu]" onnxruntime-gpu opencv-python-headless

if exist "bin\\ffmpeg.exe" set "VF_GPU_FFMPEG=%CD%\\bin\\ffmpeg.exe"
if exist "bin\\ffprobe.exe" set "VF_GPU_FFPROBE=%CD%\\bin\\ffprobe.exe"
where ffmpeg >nul 2>&1
if errorlevel 1 if "%VF_GPU_FFMPEG%"=="" (
  echo WARNING: ffmpeg.exe was not found. Copy an NVENC build to bin\\ffmpeg.exe.
)

net session >nul 2>&1
if not errorlevel 1 (
  netsh advfirewall firewall add rule name="VideoFlow GPU Worker" ^
    dir=in action=allow protocol=TCP localport=%VF_GPU_PORT% profile=private >nul
) else (
  echo WARNING: run this script as Administrator once to open the private firewall port.
)

echo Starting VideoFlow GPU worker on port %VF_GPU_PORT%...
videoflow-gpu-worker
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo Worker exited with code %EXIT_CODE%.
if "%SILENT%"=="0" pause
exit /b %EXIT_CODE%
"""


def _autostart_bat() -> str:
    return """@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
schtasks /Create /SC ONLOGON /TN "VideoFlow GPU Worker" ^
  /TR "\\"%CD%\\iniciar_gpu_worker.bat\\" --silent" /RL LIMITED /F
if errorlevel 1 (
  echo Could not register the scheduled task. Run as an administrator.
  pause
  exit /b 1
)
echo Autostart registered as "VideoFlow GPU Worker".
pause
"""


def _stop_bat() -> str:
    return """@echo off
setlocal
chcp 65001 >nul
taskkill /F /IM videoflow-gpu-worker.exe >nul 2>&1
if errorlevel 1 (
  echo No running VideoFlow GPU worker was found.
) else (
  echo VideoFlow GPU worker stopped.
)
pause
"""


def _status_ps1() -> str:
    return """param([int]$Port = 8766)
try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
  $caps = ($health.capabilities -join ',')
  Write-Output ("status=" + $health.status + " gpu=" + $health.gpu_name + " capabilities=" + $caps)
} catch {
  Write-Output "offline"
}
"""


def _status_bat() -> str:
    return """@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "worker.env" exit /b 1
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("worker.env") do (
  if not "%%~A"=="" set "%%A=%%B"
)
if "%VF_GPU_PORT%"=="" set "VF_GPU_PORT=8766"
powershell -NoP -ExecutionPolicy Bypass -File "%~dp0status_gpu_worker.ps1" -Port %VF_GPU_PORT%
pause
"""


def _readme(*, worker_id: str, has_ffmpeg: bool) -> str:
    ffmpeg_line = (
        "bin\\ffmpeg.exe is included."
        if has_ffmpeg
        else "Copy an NVENC-enabled ffmpeg.exe and ffprobe.exe into bin\\ "
        "before starting, or install FFmpeg on PATH."
    )
    return f"""VideoFlow Windows GPU Worker
=============================

Worker id: {worker_id}

1. Extract this zip to a short path, for example C:\\VideoFlowGPU.
2. Run iniciar_gpu_worker.bat. The first run installs Python 3.11, the worker,
   PyTorch CUDA, faster-whisper, rembg, and OpenCV. It can take several minutes
   and downloads from the internet.
3. If Windows Firewall asks, allow the private network. For a silent install,
   run iniciar_gpu_worker.bat once as Administrator so it can add the private
   TCP firewall rule.
4. In VideoFlow on the Linux machine, use Setup -> GPU acceleration and connect
   to this machine's LAN IP on port 8766 with the token from worker.env.
5. Optional: run instalar_autostart_windows.bat to start the worker at logon.

{ffmpeg_line}

Security:
- worker.env contains a pairing token. Do not publish this zip or paste the
  token into logs, chat, or screenshots.
- The worker is intended for a private LAN. Do not expose port 8766 to the
  internet.
- The shared mount is optional. If used, set VF_GPU_SHARED_ROOT in worker.env
  to the Windows path of the same folder mounted on Linux.

Troubleshooting:
- status_gpu_worker.bat prints health or "offline".
- parar_gpu_worker.bat stops the worker.
- If NVENC is unavailable, run: ffmpeg -hide_banner -encoders | findstr nvenc
"""


def _zip_write(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    zf.writestr(info, data)


def _add_worker_source(zf: zipfile.ZipFile) -> list[str]:
    files: list[str] = []
    pyproject = WORKER_ROOT / "pyproject.toml"
    if pyproject.is_file():
        _zip_write(zf, "worker/pyproject.toml", pyproject.read_bytes())
        files.append("worker/pyproject.toml")
    readme = WORKER_ROOT / "README.md"
    if readme.is_file():
        _zip_write(zf, "worker/README.md", readme.read_bytes())
        files.append("worker/README.md")
    source = WORKER_ROOT / "src" / "gpu_worker"
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(WORKER_ROOT).as_posix()
        _zip_write(zf, f"worker/{relative}", path.read_bytes())
        files.append(f"worker/{relative}")
    return files


def _wheel_paths() -> list[Path]:
    candidates: list[Path] = []
    for root in (ROOT / "dist", WORKER_ROOT / "dist"):
        candidates.extend(sorted(root.glob("videoflow_gpu_worker-*.whl")))
    return candidates


def build_worker_kit(
    *,
    output: Path | None = None,
    token: str = "",
    worker_id: str = "",
    shared_windows_path: str = "",
    ffmpeg_path: Path | None = None,
    include_worker_source: bool = True,
) -> KitResult:
    """Build a personal Windows worker zip and return its metadata."""

    resolved_token = (token or "").strip() or secrets.token_urlsafe(32)
    resolved_worker = (worker_id or "").strip() or f"vf-gpu-{uuid.uuid4().hex[:12]}"
    target_dir = (
        Path(output).expanduser()
        if output is not None
        else portable_home() / KIT_DIR
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"videoflow-windows-gpu-worker-{resolved_worker}.zip"
    files: list[str] = []
    ffmpeg = Path(ffmpeg_path).expanduser() if ffmpeg_path is not None else None
    has_ffmpeg = bool(ffmpeg and ffmpeg.is_file())
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        entries = {
            "worker.env": _env_file(
                token=resolved_token,
                worker_id=resolved_worker,
                shared_windows_path=shared_windows_path,
            ).encode("utf-8"),
            "iniciar_gpu_worker.bat": _crlf(_start_bat()),
            "instalar_autostart_windows.bat": _crlf(_autostart_bat()),
            "parar_gpu_worker.bat": _crlf(_stop_bat()),
            "status_gpu_worker.bat": _crlf(_status_bat()),
            "status_gpu_worker.ps1": _crlf(_status_ps1()),
            "LEIA-ME.txt": _readme(
                worker_id=resolved_worker,
                has_ffmpeg=has_ffmpeg,
            ).encode("utf-8"),
        }
        for name, data in entries.items():
            _zip_write(zf, name, data)
            files.append(name)
        if has_ffmpeg and ffmpeg is not None:
            _zip_write(zf, "bin/ffmpeg.exe", ffmpeg.read_bytes())
            files.append("bin/ffmpeg.exe")
            probe = ffmpeg.with_name("ffprobe.exe")
            if probe.is_file():
                _zip_write(zf, "bin/ffprobe.exe", probe.read_bytes())
                files.append("bin/ffprobe.exe")
        wheels = _wheel_paths()
        for wheel in wheels[:1]:
            _zip_write(zf, f"wheels/{wheel.name}", wheel.read_bytes())
            files.append(f"wheels/{wheel.name}")
        if include_worker_source:
            files.extend(_add_worker_source(zf))

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    result = KitResult(
        path=target,
        sha256=digest,
        bytes=target.stat().st_size,
        token=resolved_token,
        worker_id=resolved_worker,
        files=files,
    )
    metadata = result.to_dict(include_token=True)
    metadata["path"] = str(target)
    (target_dir / "last.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def kit_info() -> dict[str, object] | None:
    """Return the metadata of the last kit generated on this machine."""

    path = portable_home() / KIT_DIR / "last.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


__all__ = ["KitResult", "build_worker_kit", "kit_info"]
