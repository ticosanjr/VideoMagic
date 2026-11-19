"""Generate the Windows GPU worker kit.

The zip is a personal artifact: it contains the pairing token. It is generated
on demand and is never committed or attached to a public release.
"""

from __future__ import annotations

import hashlib
import json
import re
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


def _safe_worker_id(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip(".-_")
    return text[:64] or f"vf-gpu-{uuid.uuid4().hex[:12]}"


def _single_line(value: str, field: str) -> str:
    text = str(value or "").strip()
    if "\r" in text or "\n" in text:
        raise ValueError(f"{field} must be a single line")
    return text


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


def _templates_root() -> Path:
    return Path(__file__).resolve().parents[1] / "templates"


def _windows_scripts(version: str) -> dict[str, bytes]:
    scripts = _templates_root() / "windows"
    ps1 = (scripts / "VideoFlowGPU.ps1").read_text(encoding="utf-8")
    return {
        "VideoFlowGPU.ps1": _crlf(ps1.replace("__VERSION__", version)),
        "VideoFlowGPU.bat": _crlf((scripts / "VideoFlowGPU.bat").read_text(encoding="utf-8")),
        "expected_version.txt": (version + "\n").encode("utf-8"),
    }


def _readme(*, worker_id: str, has_ffmpeg: bool) -> str:
    ffmpeg_line = (
        "bin\\ffmpeg.exe is included."
        if has_ffmpeg
        else "FFmpeg is downloaded automatically if bin\\ffmpeg.exe is missing."
    )
    return f"""VideoFlow Windows GPU Worker
=============================

Worker id: {worker_id}

ONE FILE: double-click VideoFlowGPU.bat.
It opens a menu for install/repair, start, stop, status, doctor, logs,
autostart, and uninstall. The same script supports command-line actions.

First run:
1. Extract this zip to a short path, for example C:\\VideoFlowGPU.
2. Run VideoFlowGPU.bat and choose Install / update / repair.
3. The script installs uv, Python 3.11, the worker, CUDA PyTorch,
   faster-whisper, rembg, OpenCV, FFmpeg with NVENC, and the firewall rule.
4. Start the worker from the menu.
5. In VideoFlow on Linux, use Setup -> GPU acceleration with this machine's
   LAN IP, port 8766, and the token from worker.env.

Self-healing:
- Broken .venv is removed and rebuilt.
- Wrong/missing worker version is reinstalled.
- Missing CUDA/Python packages are reinstalled.
- Missing FFmpeg/NVENC is downloaded or reported clearly.
- Shared mount failure falls back to HTTP.
- The supervisor restarts the worker after a crash.
- The token is restored from worker.env.bak when possible.

{ffmpeg_line}

Security:
- worker.env contains a pairing token. Do not publish this zip or paste the
  token into logs, chat, or screenshots.
- The worker is intended for a private LAN. Do not expose port 8766 to the
  internet.
- The shared mount is optional. If used, set VF_GPU_SHARED_ROOT in worker.env
  to the Windows path of the same folder mounted on Linux.

Troubleshooting:
- VideoFlowGPU.bat -> Status / Doctor / Show logs.
- The logs are in logs/bootstrap.log and logs/worker-error.log.
- If NVIDIA driver/nvidia-smi is missing, install the NVIDIA driver and reboot.
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
    if not source.is_dir():
        return files
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(WORKER_ROOT).as_posix()
        _zip_write(zf, f"worker/{relative}", path.read_bytes())
        files.append(f"worker/{relative}")
    return files


def _wheel_paths() -> list[Path]:
    candidates: list[Path] = []
    for root in (
        _templates_root() / "wheels",
        ROOT / "dist",
        WORKER_ROOT / "dist",
    ):
        candidates.extend(sorted(root.glob("videoflow_gpu_worker-*.whl")))
    return candidates


def _kit_version() -> str:
    from videoflow import __version__

    return str(__version__)


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

    resolved_token = _single_line(token, "token") or secrets.token_urlsafe(32)
    resolved_worker = _safe_worker_id(worker_id)
    shared_windows_path = _single_line(shared_windows_path, "shared_windows_path")
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
            "LEIA-ME.txt": _readme(
                worker_id=resolved_worker,
                has_ffmpeg=has_ffmpeg,
            ).encode("utf-8"),
            **_windows_scripts(_kit_version()),
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
    metadata = result.to_dict(include_token=False)
    metadata["path"] = str(target)
    metadata["token_location"] = "worker.env inside the zip"
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
