"""Runtime configuration for the isolated GPU worker."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8766
DEFAULT_MAX_UPLOAD_MB = 8192
DEFAULT_MAX_QUEUE = 16
DEFAULT_MODEL_TTL_SEC = 300.0
DEFAULT_MAX_VRAM_MB = 10_240
DEFAULT_VRAM_RESERVE_MB = 512
DEFAULT_ADVERTISE_PORT = 8767


def default_work_dir() -> Path:
    """Return the default on-disk home for artifacts, jobs, and the database."""

    return Path.home() / ".videoflow" / "gpu-worker"


def _env(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_int(
    environ: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    raw = _env(environ, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum or (maximum is not None and value > maximum):
        bounds = f">= {minimum}" if maximum is None else f"between {minimum} and {maximum}"
        raise ValueError(f"{name} must be {bounds}, got {value}")
    return value


def _env_float(
    environ: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float = 0.0,
) -> float:
    raw = _env(environ, name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def _env_path(environ: Mapping[str, str], name: str) -> Path | None:
    raw = _env(environ, name)
    return Path(raw).expanduser() if raw is not None else None


def _env_bool(environ: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = _env(environ, name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(environ: Mapping[str, str], name: str) -> tuple[str, ...]:
    raw = _env(environ, name)
    if raw is None:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable worker configuration.

    Units are deliberately flat so the app factory and tests can build settings without
    touching ``os.environ``.
    """

    token: str | None = None
    allow_lan_open: bool = False
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    worker_id: str = ""
    work_dir: Path = field(default_factory=default_work_dir)
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB
    max_queue: int = DEFAULT_MAX_QUEUE
    cpu_workers: int = 2
    warmup: bool = False
    token_only: bool = False
    allowed_clients: tuple[str, ...] = ()
    log_max_mb: int = 20
    metrics_retention_hours: float = 720.0
    job_retention_hours: float = 168.0
    min_free_disk_mb: int = 2048
    model_ttl_sec: float = DEFAULT_MODEL_TTL_SEC
    max_vram_mb: int = DEFAULT_MAX_VRAM_MB
    vram_reserve_mb: int = DEFAULT_VRAM_RESERVE_MB
    discovery: bool = False
    advertise_port: int = DEFAULT_ADVERTISE_PORT
    shared_root: Path | None = None
    chatterbox_cmd: str | None = None
    ace_step_cmd: str | None = None
    stable_audio_cmd: str | None = None
    audio_separator_cmd: str | None = None
    realesrgan_cmd: str | None = None
    asr_cmd: str | None = None
    diarize_cmd: str | None = None
    comfyui_url: str | None = None
    builtin_handlers: bool = False
    ffmpeg_cmd: str | None = None
    asr_model: str = "large-v3-turbo"
    asr_device: str = "cuda"
    asr_compute_type: str = "float16"
    asr_cpu_threads: int = 0
    asr_num_workers: int = 1

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Build settings from ``VF_*`` variables."""

        values = os.environ if environ is None else environ
        work_dir = _env_path(values, "VF_GPU_WORK_DIR") or default_work_dir()
        return cls(
            token=_env(values, "VF_GPU_TOKEN"),
            allow_lan_open=_env_bool(values, "VF_GPU_ALLOW_LAN_OPEN", False),
            host=_env(values, "VF_GPU_HOST") or DEFAULT_HOST,
            port=_env_int(values, "VF_GPU_PORT", DEFAULT_PORT, minimum=1, maximum=65535),
            worker_id=_env(values, "VF_GPU_WORKER_ID") or "",
            work_dir=work_dir,
            max_upload_mb=_env_int(
                values, "VF_GPU_MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB, minimum=1
            ),
            max_queue=_env_int(values, "VF_GPU_MAX_QUEUE", DEFAULT_MAX_QUEUE, minimum=0),
            cpu_workers=_env_int(values, "VF_GPU_CPU_WORKERS", 2, minimum=1, maximum=8),
            warmup=_env_bool(values, "VF_GPU_WARMUP", False),
            token_only=_env_bool(values, "VF_GPU_TOKEN_ONLY", False),
            allowed_clients=_env_list(values, "VF_GPU_ALLOWED_CLIENTS"),
            log_max_mb=_env_int(values, "VF_GPU_LOG_MAX_MB", 20, minimum=1),
            metrics_retention_hours=_env_float(
                values, "VF_GPU_METRICS_RETENTION_HOURS", 720.0, minimum=1.0
            ),
            job_retention_hours=_env_float(
                values, "VF_GPU_JOB_RETENTION_HOURS", 168.0, minimum=1.0
            ),
            min_free_disk_mb=_env_int(
                values, "VF_GPU_MIN_FREE_DISK_MB", 2048, minimum=0
            ),
            model_ttl_sec=_env_float(
                values, "VF_GPU_MODEL_TTL_SEC", DEFAULT_MODEL_TTL_SEC, minimum=0.0
            ),
            max_vram_mb=_env_int(
                values, "VF_GPU_MAX_VRAM_MB", DEFAULT_MAX_VRAM_MB, minimum=0
            ),
            vram_reserve_mb=_env_int(
                values, "VF_GPU_VRAM_RESERVE_MB", DEFAULT_VRAM_RESERVE_MB, minimum=0
            ),
            discovery=_env_bool(values, "VF_GPU_DISCOVERY", True),
            advertise_port=_env_int(
                values,
                "VF_GPU_ADVERTISE_PORT",
                DEFAULT_ADVERTISE_PORT,
                minimum=1,
                maximum=65535,
            ),
            shared_root=_env_path(values, "VF_GPU_SHARED_ROOT"),
            chatterbox_cmd=_env(values, "VF_CHATTERBOX_CMD"),
            ace_step_cmd=_env(values, "VF_ACE_STEP_CMD"),
            stable_audio_cmd=_env(values, "VF_STABLE_AUDIO_CMD"),
            audio_separator_cmd=_env(values, "VF_AUDIO_SEPARATOR_CMD"),
            realesrgan_cmd=_env(values, "VF_REALESRGAN_CMD"),
            asr_cmd=_env(values, "VF_GPU_ASR_CMD"),
            diarize_cmd=_env(values, "VF_GPU_DIARIZE_CMD"),
            comfyui_url=_env(values, "VF_GPU_COMFYUI_URL") or _env(values, "VF_COMFYUI_URL"),
            builtin_handlers=_env_bool(values, "VF_GPU_BUILTIN_HANDLERS", False),
            ffmpeg_cmd=_env(values, "VF_GPU_FFMPEG"),
            asr_model=_env(values, "VF_GPU_ASR_MODEL") or "large-v3-turbo",
            asr_device=_env(values, "VF_GPU_ASR_DEVICE") or "cuda",
            asr_compute_type=_env(values, "VF_GPU_ASR_COMPUTE_TYPE") or "float16",
            asr_cpu_threads=_env_int(values, "VF_GPU_ASR_CPU_THREADS", 0, minimum=0),
            asr_num_workers=_env_int(values, "VF_GPU_ASR_NUM_WORKERS", 1, minimum=1, maximum=8),
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024
