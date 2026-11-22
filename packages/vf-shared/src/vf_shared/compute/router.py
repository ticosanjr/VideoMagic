"""Decide whether a capability should run remotely or locally."""

from __future__ import annotations

from typing import Any

from vf_shared.compute.client import GPUWorkerClient
from vf_shared.compute.config import load_gpu_config
from vf_shared.compute.errors import WorkerOfflineError
from vf_shared.compute.models import WorkerHealth

from .router_common import (
    _DEFAULT_CIRCUIT_SEC,
    _DEFAULT_DISCOVERY_TIMEOUT,
    _DEFAULT_HEALTH_TIMEOUT,
    _DEFAULT_HEALTH_TTL,
    _DEFAULT_MAX_QUEUE,
    _DEFAULT_MAX_UTILIZATION,
    _DEFAULT_MIN_VRAM_MB,
    _DEFAULT_MODE,
    _env_bool,
    _env_float,
    _env_int,
    _env_str,
)
from .router_execute import RouterExecuteMixin
from .router_health import RouterHealthMixin
from .router_submit import RouterSubmitMixin

COMPUTE_MODES = ("auto", "local_only", "remote_preferred")


class ComputeRouter(RouterHealthMixin, RouterExecuteMixin, RouterSubmitMixin):
    """Decide and execute a capability locally or on the GPU worker."""

    def __init__(
        self,
        *,
        mode: str = _DEFAULT_MODE,
        worker_url: str = "",
        token: str = "",
        transport: str = "auto",
        shared_local_root: str = "",
        health_ttl: float = _DEFAULT_HEALTH_TTL,
        health_timeout: float = _DEFAULT_HEALTH_TIMEOUT,
        min_vram_mb: int = _DEFAULT_MIN_VRAM_MB,
        max_queue: int = _DEFAULT_MAX_QUEUE,
        max_gpu_utilization: float = _DEFAULT_MAX_UTILIZATION,
        circuit_sec: float = _DEFAULT_CIRCUIT_SEC,
        fallback_local: bool = True,
        allowed_capabilities: set[str] | None = None,
        client: GPUWorkerClient | None = None,
        discovery_enabled: bool = True,
        discovery_timeout: float = _DEFAULT_DISCOVERY_TIMEOUT,
        worker_source: str = "",
        offline_error: type[Exception] | None = None,
    ) -> None:
        normalized_mode = (mode or _DEFAULT_MODE).strip().lower()
        if normalized_mode not in COMPUTE_MODES:
            raise ValueError(f"invalid compute mode: {mode!r}")
        self.mode = normalized_mode
        self.worker_url = worker_url.strip().rstrip("/")
        self.token = token
        self.transport = str(transport or "auto").strip().lower()
        if self.transport not in {"auto", "http", "shared"}:
            self.transport = "auto"
        self.shared_local_root = str(shared_local_root or "").strip()
        self.upload_workers = max(1, min(_env_int("VF_GPU_UPLOAD_WORKERS", 3), 8))
        self.health_ttl = max(float(health_ttl), 0.0)
        self.health_timeout = max(float(health_timeout), 0.0)
        self.min_vram_mb = max(int(min_vram_mb), 0)
        self.max_queue = max(int(max_queue), 0)
        self.max_gpu_utilization = max(0.0, min(100.0, float(max_gpu_utilization)))
        self.circuit_sec = max(float(circuit_sec), 0.0)
        self.fallback_local = bool(fallback_local)
        self.allowed_capabilities = (
            {str(item).lower() for item in allowed_capabilities}
            if allowed_capabilities is not None
            else None
        )
        self._client = client
        self._health: WorkerHealth | None = None
        self._worker_id = ""
        self._health_at = 0.0
        self._circuit_until = 0.0
        self.discovery_enabled = bool(discovery_enabled)
        self.discovery_timeout = max(0.1, float(discovery_timeout))
        self._discovery_at = 0.0
        self._discovery_reason = ""
        normalized_source = str(worker_source or "").strip().lower()
        if normalized_source not in {"settings", "mdns", "env", "none"}:
            normalized_source = "settings" if self.worker_url else "none"
        self.worker_source = normalized_source
        self.offline_error = offline_error or WorkerOfflineError


    @classmethod
    def from_env(cls, *, client: GPUWorkerClient | None = None) -> ComputeRouter:
        """Build a router from env + the shared ``gpu.json`` config."""

        config = load_gpu_config()
        return cls(
            mode=config.mode,
            worker_url=config.worker_url,
            token=config.token,
            transport=config.transport,
            shared_local_root=_env_str("VF_GPU_SHARED_LOCAL_ROOT"),
            health_ttl=_env_float("VF_GPU_HEALTH_TTL_SEC", _DEFAULT_HEALTH_TTL),
            health_timeout=_env_float("VF_GPU_HEALTH_TIMEOUT_SEC", _DEFAULT_HEALTH_TIMEOUT),
            min_vram_mb=_env_int("VF_GPU_MIN_VRAM_MB", _DEFAULT_MIN_VRAM_MB),
            max_queue=_env_int("VF_GPU_MAX_QUEUE", _DEFAULT_MAX_QUEUE),
            max_gpu_utilization=_env_float(
                "VF_GPU_MAX_UTILIZATION", _DEFAULT_MAX_UTILIZATION
            ),
            circuit_sec=_env_float("VF_GPU_CIRCUIT_SEC", _DEFAULT_CIRCUIT_SEC),
            client=client,
            discovery_enabled=_env_bool("VF_GPU_DISCOVERY", True),
            discovery_timeout=_env_float(
                "VF_GPU_DISCOVERY_TIMEOUT_SEC", _DEFAULT_DISCOVERY_TIMEOUT
            ),
            worker_source=(
                "env"
                if config.source == "env"
                else ("settings" if config.worker_url else "none")
            ),
        )


    @property
    def client(self) -> GPUWorkerClient:
        """Lazily constructed worker client."""

        if self._client is None:
            if not self.worker_url:
                raise RuntimeError("VF_GPU_WORKER_URL is not configured")
            self._client = GPUWorkerClient(self.worker_url, self.token)
        return self._client


    def invalidate(self) -> None:
        """Forget cached health and close the circuit."""

        self._health = None
        self._health_at = 0.0
        self._circuit_until = 0.0


    def set_worker(self, url: str, token: str = "", *, worker_id: str = "") -> None:
        """Point the router at a worker without rebuilding the process."""

        self.worker_url = str(url or "").strip().rstrip("/")
        self.token = str(token or "")
        self._worker_id = str(worker_id or "")
        if self._client is not None:
            self._client.close()
        self._client = None
        self.invalidate()


    def disconnect(self) -> None:
        """Drop the current worker and fall back to local execution."""

        self.set_worker("", "")


    def discover(self, *, timeout_sec: float = 1.5) -> list[dict[str, Any]]:
        """Listen for LAN beacons and return the peers seen."""

        from vf_shared.compute.discovery import discover_workers

        return discover_workers(timeout_sec=timeout_sec)


    @property
    def execution_node(self) -> str:
        """Stable node label for the last healthy placement."""

        if self.mode == "local_only":
            return "local"
        health = self._health
        if health is None or not health.available:
            return "local"
        identifier = health.worker_id or health.hostname or self._worker_id
        return f"remote_gpu:{identifier}" if identifier else "remote_gpu"
