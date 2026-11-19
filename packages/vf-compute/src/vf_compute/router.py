"""Decide whether a capability should run remotely or locally."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

from vf_compute.capabilities import vram_cost
from vf_compute.client import GPUWorkerClient
from vf_compute.models import WorkerDecision, WorkerHealth

COMPUTE_MODES = ("auto", "local_only", "remote_preferred")

_DEFAULT_MODE = "auto"
_DEFAULT_HEALTH_TTL = 1.0
_DEFAULT_HEALTH_TIMEOUT = 0.3
_DEFAULT_MIN_VRAM_MB = 2048
_DEFAULT_MAX_QUEUE = 2
_DEFAULT_CIRCUIT_SEC = 2.0


def _env_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _local(reason: str, capability: str) -> WorkerDecision:
    return WorkerDecision(
        mode="local",
        reason=reason,
        capability=capability,
        execution_node="local",
    )


class ComputeRouter:
    """Environment-driven compute placement policy with a health cache.

    ``local_only`` never performs network I/O. ``auto`` and
    ``remote_preferred`` both use the worker when it is healthy, advertises
    the capability, has enough free VRAM and is not over its queue limit;
    otherwise they fall back to local execution with a reason.
    """

    def __init__(
        self,
        *,
        mode: str = _DEFAULT_MODE,
        worker_url: str = "",
        token: str = "",
        health_ttl: float = _DEFAULT_HEALTH_TTL,
        health_timeout: float = _DEFAULT_HEALTH_TIMEOUT,
        min_vram_mb: int = _DEFAULT_MIN_VRAM_MB,
        max_queue: int = _DEFAULT_MAX_QUEUE,
        circuit_sec: float = _DEFAULT_CIRCUIT_SEC,
        client: GPUWorkerClient | None = None,
    ) -> None:
        normalized_mode = (mode or _DEFAULT_MODE).strip().lower()
        if normalized_mode not in COMPUTE_MODES:
            raise ValueError(f"invalid compute mode: {mode!r}")
        self.mode = normalized_mode
        self.worker_url = worker_url.strip().rstrip("/")
        self.token = token
        self.health_ttl = max(float(health_ttl), 0.0)
        self.health_timeout = max(float(health_timeout), 0.0)
        self.min_vram_mb = max(int(min_vram_mb), 0)
        self.max_queue = max(int(max_queue), 0)
        self.circuit_sec = max(float(circuit_sec), 0.0)
        self._client = client
        self._health: WorkerHealth | None = None
        self._worker_id = ""
        self._health_at = 0.0
        self._circuit_until = 0.0

    @classmethod
    def from_env(cls, *, client: GPUWorkerClient | None = None) -> ComputeRouter:
        """Build a router from ``VF_*`` environment variables."""

        return cls(
            mode=_env_str("VF_COMPUTE_MODE", _DEFAULT_MODE),
            worker_url=_env_str("VF_GPU_WORKER_URL"),
            token=_env_str("VF_GPU_WORKER_TOKEN"),
            health_ttl=_env_float("VF_GPU_HEALTH_TTL_SEC", _DEFAULT_HEALTH_TTL),
            health_timeout=_env_float("VF_GPU_HEALTH_TIMEOUT_SEC", _DEFAULT_HEALTH_TIMEOUT),
            min_vram_mb=_env_int("VF_GPU_MIN_VRAM_MB", _DEFAULT_MIN_VRAM_MB),
            max_queue=_env_int("VF_GPU_MAX_QUEUE", _DEFAULT_MAX_QUEUE),
            circuit_sec=_env_float("VF_GPU_CIRCUIT_SEC", _DEFAULT_CIRCUIT_SEC),
            client=client,
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

        from vf_compute.discovery import discover_workers

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

    def health(self, force: bool = False) -> WorkerHealth:
        """Return worker health using a TTL cache and circuit breaker.

        ``force=True`` probes immediately, bypassing both the cache and an open
        circuit. Network failures open the circuit for ``circuit_sec``.
        """

        if self.mode == "local_only":
            return WorkerHealth(available=False, message="local_only mode")

        now = time.monotonic()
        if not force:
            if self._health is not None and now - self._health_at < self.health_ttl:
                return self._health
            if now < self._circuit_until:
                if self._health is not None:
                    return self._health
                return WorkerHealth(available=False, message="worker circuit open")

        if not self.worker_url and self._client is None:
            health = WorkerHealth(
                available=False,
                message="VF_GPU_WORKER_URL is not configured",
            )
            self._health = health
            self._health_at = now
            return health

        try:
            health = self.client.health(timeout=self.health_timeout)
        except Exception as exc:  # noqa: BLE001 - any transport failure opens the circuit
            health = WorkerHealth(available=False, message=f"worker unreachable: {exc}")
            self._circuit_until = now + self.circuit_sec

        self._health = health
        self._health_at = time.monotonic()
        return health

    def _remote_block_reason(
        self,
        health: WorkerHealth,
        capability: str,
        required_vram_mb: int,
    ) -> str | None:
        if not health.available:
            detail = f": {health.message}" if health.message else ""
            return f"remote worker unavailable{detail}"
        if capability:
            offered = {item.lower() for item in health.capabilities}
            if capability.lower() not in offered:
                return f"capability not available remotely: {capability}"
        required = max(int(required_vram_mb), self.min_vram_mb, 0)
        if required > health.vram_free_mb:
            return (
                f"insufficient vram: need {required} MB, "
                f"free {health.vram_free_mb} MB"
            )
        if health.queue_depth >= self.max_queue:
            return f"worker queue full: {health.queue_depth}/{self.max_queue}"
        return None

    def decide(self, capability: str, required_vram_mb: int = 0) -> WorkerDecision:
        """Choose ``remote`` or ``local`` for one capability request."""

        capability = str(capability or "")
        if self.mode == "local_only":
            return _local("local_only mode", capability)

        health = self.health()
        required = max(int(required_vram_mb or 0), vram_cost(capability), 0)
        reason = self._remote_block_reason(health, capability, required)
        if reason is not None:
            return _local(reason, capability)
        return WorkerDecision(
            mode="remote",
            reason=f"remote worker selected for {capability or 'default'}",
            capability=capability,
            execution_node=self.execution_node,
        )

    def execute(
        self,
        capability: str,
        remote_fn: Any,
        local_fn: Any,
        *,
        required_vram_mb: int = 0,
    ) -> dict[str, Any]:
        """Run remotely when possible, falling back locally on any failure.

        The return value keeps the caller's payload under ``value`` and records
        the placement, fallback reason, and elapsed time for job telemetry.
        """

        decision = self.decide(capability, required_vram_mb)
        if decision.is_remote:
            started = time.perf_counter()
            try:
                value = remote_fn()
            except Exception as exc:  # noqa: BLE001 - fallback is the contract
                self.invalidate()
                reason = f"remote failed: {exc}"
            else:
                return {
                    "value": value,
                    "execution_node": decision.execution_node,
                    "fallback_reason": "",
                    "remote": True,
                    "elapsed_sec": round(time.perf_counter() - started, 4),
                }
        else:
            reason = decision.reason
        started = time.perf_counter()
        value = local_fn()
        return {
            "value": value,
            "execution_node": "local",
            "fallback_reason": reason,
            "remote": False,
            "elapsed_sec": round(time.perf_counter() - started, 4),
        }

    def submit(
        self,
        capability: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """Submit a capability job, wait, and download its first artifact.

        This is the small-job path. Large artifacts should use the shared
        mount path added in the transport stage.
        """

        body = dict(payload or {})
        decision = self.decide(capability, int(body.get("required_vram_mb") or 0))
        if not decision.is_remote:
            raise RuntimeError(decision.reason)
        params = body.get("params")
        if not isinstance(params, dict):
            params = {
                key: value
                for key, value in body.items()
                if key not in {"inputs", "shared_inputs", "timeout_sec"}
            }
        inputs = [str(item) for item in body.get("inputs", []) or []]
        shared_inputs = [str(item) for item in body.get("shared_inputs", []) or []]
        shared_outputs = [str(item) for item in body.get("shared_outputs", []) or []]
        job_id = self.client.submit(
            capability,
            params=params,
            inputs=inputs,
            shared_inputs=shared_inputs,
            shared_outputs=shared_outputs,
            shared_root=str(body.get("shared_root") or "") or None,
        )
        status = self.client.wait(
            job_id,
            timeout=float(body.get("timeout_sec") or timeout),
        )
        if not status.ok:
            raise RuntimeError(
                f"remote job {job_id} ended in {status.state}: {status.error or status.message}"
            )
        if not status.artifacts:
            raise RuntimeError(f"remote job {job_id} returned no artifacts")
        if status.shared_artifacts and body.get("shared_root"):
            shared_path = Path(str(body["shared_root"])) / status.shared_artifacts[0]
            if shared_path.is_file():
                return {
                    "path": str(shared_path),
                    "job_id": job_id,
                    "execution_node": decision.execution_node,
                    "artifacts": list(status.artifacts),
                    "shared_artifacts": list(status.shared_artifacts),
                    "transport": "shared_mount",
                }
        name = status.artifacts[0]
        target = Path(tempfile.mkdtemp(prefix="vf-remote-")) / Path(name).name
        self.client.download(job_id, name, target)
        return {
            "path": str(target),
            "job_id": job_id,
            "execution_node": decision.execution_node,
            "artifacts": list(status.artifacts),
            "shared_artifacts": list(status.shared_artifacts),
            "transport": "lan_stream",
        }


__all__ = ["COMPUTE_MODES", "ComputeRouter"]
