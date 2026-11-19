"""Data contracts shared by the compute router and GPU worker client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ComputeMode = Literal["remote", "local"]
JobState = Literal["queued", "running", "succeeded", "failed", "cancelled"]


def _as_mapping(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return {str(key): value for key, value in payload.items()}
    raise TypeError("worker payload must be a mapping")


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            names.append(str(item.get("name") or item.get("id") or item))
        else:
            names.append(str(item))
    return names


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class WorkerHealth(BaseModel):
    """Snapshot of a GPU worker's availability and capacity."""

    model_config = ConfigDict(extra="ignore")

    available: bool = False
    gpu_name: str = ""
    vram_free_mb: int = 0
    vram_total_mb: int = 0
    vram_used_mb: int = 0
    gpu_utilization: float = 0.0
    temperature_c: float = 0.0
    capabilities: list[str] = Field(default_factory=list)
    models_loaded: list[str] = Field(default_factory=list)
    queue_depth: int = 0
    message: str = ""
    worker_id: str = ""
    hostname: str = ""
    ip_local: str = ""
    port: int = 0
    status: str = ""
    version: str = ""
    platform: str = ""
    shared_root: str = ""
    auth_mode: str = ""
    nvenc: bool = False
    encoder: str = ""

    @model_validator(mode="before")
    @classmethod
    def _accept_aliases(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        if "models" in data and "models_loaded" not in data:
            data["models_loaded"] = data.pop("models")
        if "loaded_models" in data and "models_loaded" not in data:
            data["models_loaded"] = data.pop("loaded_models")
        return data

    @property
    def models(self) -> list[str]:
        """Alias for :attr:`models_loaded`."""

        return self.models_loaded

    def __bool__(self) -> bool:
        return self.available

    @classmethod
    def from_payload(cls, payload: Any) -> WorkerHealth:
        """Build health from a worker payload, tolerating common variants."""

        data = _as_mapping(payload)
        if "available" in data:
            available = bool(data["available"])
        elif "ok" in data:
            available = bool(data["ok"])
        elif "status" in data:
            available = str(data["status"]).lower() in {"ok", "healthy", "ready", "up"}
        else:
            available = True

        message = data.get("message") or data.get("detail") or data.get("error") or ""
        return cls(
            available=available,
            gpu_name=str(data.get("gpu_name") or data.get("gpu") or ""),
            vram_free_mb=_as_int(data.get("vram_free_mb", data.get("vram_free"))),
            vram_total_mb=_as_int(data.get("vram_total_mb", data.get("vram_total"))),
            capabilities=_as_str_list(data.get("capabilities")),
            models_loaded=_as_str_list(
                data.get("models_loaded", data.get("models", data.get("loaded_models")))
            ),
            queue_depth=_as_int(data.get("queue_depth", data.get("queue"))),
            message=str(message),
            worker_id=str(data.get("worker_id") or data.get("id") or ""),
            hostname=str(data.get("hostname") or data.get("host") or ""),
            ip_local=str(data.get("ip_local") or data.get("ip") or ""),
            port=_as_int(data.get("port")),
            status=str(data.get("status") or ""),
            version=str(data.get("version") or ""),
            platform=str(data.get("platform") or ""),
            shared_root=str(data.get("shared_root") or ""),
            auth_mode=str(data.get("auth_mode") or ""),
            nvenc=bool(data.get("nvenc", False)),
            encoder=str(data.get("encoder") or ""),
            vram_used_mb=_as_int(data.get("vram_used_mb", data.get("vram_used"))),
            gpu_utilization=_as_float(
                data.get("gpu_utilization", data.get("gpu_util"))
            ),
            temperature_c=_as_float(
                data.get("temperature_c", data.get("temperature"))
            ),
        )


class WorkerDecision(BaseModel):
    """Placement decision for one capability request."""

    model_config = ConfigDict(extra="ignore")

    mode: ComputeMode
    reason: str
    capability: str = ""
    execution_node: str = ""

    @property
    def is_remote(self) -> bool:
        return self.mode == "remote"

    @property
    def is_local(self) -> bool:
        return self.mode == "local"


class JobStatus(BaseModel):
    """Status of a job submitted to a GPU worker."""

    model_config = ConfigDict(extra="ignore")

    TERMINAL_STATES: ClassVar[frozenset[str]] = frozenset(
        {"succeeded", "failed", "cancelled", "canceled", "done", "error"}
    )

    job_id: str
    state: str = "queued"
    progress: float = 0.0
    message: str = ""
    artifacts: list[str] = Field(default_factory=list)
    shared_artifacts: list[str] = Field(default_factory=list)
    shared_error: str | None = None
    error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_aliases(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        if "id" in data and "job_id" not in data:
            data["job_id"] = data.pop("id")
        if "status" in data and "state" not in data:
            data["state"] = data.pop("status")
        return data

    @property
    def done(self) -> bool:
        return self.state.lower() in self.TERMINAL_STATES

    @property
    def ok(self) -> bool:
        return self.state.lower() in {"succeeded", "done"}

    @classmethod
    def from_payload(cls, payload: Any, job_id: str = "") -> JobStatus:
        data = _as_mapping(payload)
        resolved_id = str(data.get("job_id") or data.get("id") or job_id)
        state = str(data.get("state") or data.get("status") or "queued").lower()
        artifacts = data.get("artifacts")
        if artifacts is None:
            artifacts = data.get("outputs", [])
        if isinstance(artifacts, Mapping):
            artifacts = list(artifacts)
        error = data.get("error")
        return cls(
            job_id=resolved_id,
            state=state,
            progress=_as_float(data.get("progress")),
            message=str(data.get("message") or data.get("detail") or ""),
            artifacts=_as_str_list(artifacts),
            shared_artifacts=_as_str_list(
                data.get("shared_artifacts", data.get("shared_outputs"))
            ),
            shared_error=(
                str(data["shared_error"])
                if data.get("shared_error") is not None
                else None
            ),
            error=str(error) if error is not None else None,
        )


__all__ = ["ComputeMode", "JobState", "JobStatus", "WorkerDecision", "WorkerHealth"]
