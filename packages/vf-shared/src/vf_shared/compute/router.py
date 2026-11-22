"""Decide whether a capability should run remotely or locally."""

from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from vf_shared.compute.capabilities import vram_cost
from vf_shared.compute.client import GPUWorkerClient
from vf_shared.compute.config import load_gpu_config
from vf_shared.compute.execution import ExecutionRecord, now_iso
from vf_shared.compute.models import WorkerDecision, WorkerHealth

COMPUTE_MODES = ("auto", "local_only", "remote_preferred")

_DEFAULT_MODE = "auto"
_DEFAULT_HEALTH_TTL = 1.0
_DEFAULT_HEALTH_TIMEOUT = 0.3
_DEFAULT_MIN_VRAM_MB = 2048
_DEFAULT_MAX_QUEUE = 2
_DEFAULT_CIRCUIT_SEC = 2.0
_DEFAULT_DISCOVERY_TIMEOUT = 0.8
_DISCOVERY_TTL = 5.0


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


def _env_bool(name: str, default: bool = True) -> bool:
    raw = _env_str(name)
    if not raw:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def _valid_shared_file(path: Path) -> bool:
    """Wait briefly for SMB metadata and require a non-empty file."""

    for _attempt in range(3):
        try:
            if path.is_file() and path.stat().st_size > 0:
                return True
        except OSError:
            pass
        time.sleep(0.25)
    return False


def _shared_relative(root: str | Path | None, value: str) -> str:
    """Return ``value`` relative to a local shared mount, or ``""``."""

    if not root:
        return ""
    try:
        base = Path(root).expanduser().resolve()
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            return ""
        return path.relative_to(base).as_posix()
    except (OSError, ValueError):
        return ""


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
        transport: str = "auto",
        shared_local_root: str = "",
        health_ttl: float = _DEFAULT_HEALTH_TTL,
        health_timeout: float = _DEFAULT_HEALTH_TIMEOUT,
        min_vram_mb: int = _DEFAULT_MIN_VRAM_MB,
        max_queue: int = _DEFAULT_MAX_QUEUE,
        circuit_sec: float = _DEFAULT_CIRCUIT_SEC,
        fallback_local: bool = True,
        allowed_capabilities: set[str] | None = None,
        client: GPUWorkerClient | None = None,
        discovery_enabled: bool = True,
        discovery_timeout: float = _DEFAULT_DISCOVERY_TIMEOUT,
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
            circuit_sec=_env_float("VF_GPU_CIRCUIT_SEC", _DEFAULT_CIRCUIT_SEC),
            client=client,
            discovery_enabled=_env_bool("VF_GPU_DISCOVERY", True),
            discovery_timeout=_env_float(
                "VF_GPU_DISCOVERY_TIMEOUT_SEC", _DEFAULT_DISCOVERY_TIMEOUT
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
            if self.discovery_enabled and now - self._discovery_at >= _DISCOVERY_TTL:
                self._discovery_at = now
                try:
                    peers = self.discover(timeout_sec=self.discovery_timeout)
                except Exception as exc:  # noqa: BLE001 - discovery is best-effort
                    peers = []
                    self._discovery_reason = f"discovery failed: {exc}"
                peer = next(
                    (item for item in peers if str(item.get("url") or "").strip()),
                    None,
                )
                if peer is not None:
                    self.worker_url = str(peer["url"]).strip().rstrip("/")
                    if peer.get("token"):
                        self.token = str(peer["token"])
                    self._worker_id = str(peer.get("worker_id") or "")
                    self._discovery_reason = "worker discovered on the LAN"
            if not self.worker_url and self._client is None:
                health = WorkerHealth(
                    available=False,
                    message=(
                        "worker not configured"
                        + (f": {self._discovery_reason}" if self._discovery_reason else "")
                    ),
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
        if (
            capability
            and self.allowed_capabilities is not None
            and capability.lower() not in self.allowed_capabilities
        ):
            return f"capability disabled in GPU settings: {capability}"
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
        fallback_local: bool = True,
    ) -> dict[str, Any]:
        """Run remotely when possible, falling back locally on any failure.

        The return value keeps the caller's payload under ``value`` and records
        the placement, fallback reason, and elapsed time for job telemetry.
        """

        decision = self.decide(capability, required_vram_mb)
        started_at = now_iso()
        if decision.is_remote:
            started = time.perf_counter()
            try:
                value = remote_fn()
            except Exception as exc:  # noqa: BLE001 - fallback is the contract
                self.invalidate()
                if not fallback_local:
                    raise
                reason = f"remote failed: {exc}"
            else:
                elapsed = time.perf_counter() - started
                execution = ExecutionRecord(
                    run_id="",
                    capability=capability,
                    execution_node=decision.execution_node,
                    device="remote_gpu",
                    degraded=False,
                    started_at=started_at,
                    finished_at=now_iso(),
                    elapsed_sec=elapsed,
                )
                return {
                    "value": value,
                    "execution_node": decision.execution_node,
                    "fallback_reason": "",
                    "remote": True,
                    "degraded": False,
                    "degraded_reason": "",
                    "elapsed_sec": round(elapsed, 4),
                    "execution": execution.to_dict(),
                }
        else:
            reason = decision.reason
        started = time.perf_counter()
        value = local_fn()
        elapsed = time.perf_counter() - started
        degraded = self.mode != "local_only"
        execution = ExecutionRecord(
            run_id="",
            capability=capability,
            execution_node="local",
            device="cpu",
            degraded=degraded,
            degraded_reason=reason,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=elapsed,
        )
        return {
            "value": value,
            "execution_node": "local",
            "fallback_reason": reason,
            "remote": False,
            "degraded": degraded,
            "degraded_reason": reason,
            "elapsed_sec": round(elapsed, 4),
            "execution": execution.to_dict(),
        }

    def _prepare_remote_inputs(self, inputs: list[str]) -> list[str]:
        upload = getattr(self.client, "upload_artifact", None)
        if not callable(upload):
            return inputs
        prepared: list[str | None] = [None] * len(inputs)
        pending: list[tuple[int, str, Path]] = []
        known: dict[str, str] = {}
        for index, item in enumerate(inputs):
            try:
                path = Path(item).expanduser()
                if not path.is_file():
                    prepared[index] = item
                    continue
                resolved = str(path.resolve())
            except OSError:
                prepared[index] = item
                continue
            existing = known.get(resolved)
            if existing is not None:
                prepared[index] = existing
                continue
            pending.append((index, resolved, path))
        if not pending:
            return [item for item in prepared if item is not None]
        if len(pending) > 1 and self.upload_workers > 1:
            with ThreadPoolExecutor(max_workers=self.upload_workers) as pool:
                uploaded = list(pool.map(lambda item: str(upload(item[2])), pending))
        else:
            uploaded = [str(upload(item[2])) for item in pending]
        for (index, resolved, _path), artifact_id in zip(pending, uploaded, strict=True):
            known[resolved] = artifact_id
            prepared[index] = artifact_id
        return [item if item is not None else "" for item in prepared]

    def _prepare_remote_params(
        self,
        params: dict[str, Any],
        inputs: list[str],
        shared_placeholders: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Upload local files referenced by params and replace them by placeholders.

        The worker rewrites ``__VF_INPUT_n__`` to the materialized input path
        before calling the handler, so command templates and Python handlers see
        a real local path on the GPU machine. Files already reachable through a
        shared mount keep their index without an upload.
        """

        upload = getattr(self.client, "upload_artifact", None)
        if not callable(upload):
            return params
        cache: dict[str, str] = dict(shared_placeholders or {})

        def walk(value: Any) -> Any:
            if isinstance(value, str):
                try:
                    path = Path(value).expanduser()
                    if not path.is_file():
                        return value
                    resolved = str(path.resolve())
                except OSError:
                    return value
                placeholder = cache.get(resolved)
                if placeholder is not None:
                    return placeholder
                artifact_id = str(upload(path))
                index = len(inputs)
                inputs.append(artifact_id)
                placeholder = f"__VF_INPUT_{index}__"
                cache[resolved] = placeholder
                return placeholder
            if isinstance(value, dict):
                return {str(key): walk(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [walk(item) for item in value]
            return value

        return walk(params)

    def _transfer_summary(self) -> dict[str, Any]:
        stats = getattr(self.client, "transfer_stats", {}) or {}
        upload_bytes = int(stats.get("upload_bytes") or 0)
        download_bytes = int(stats.get("download_bytes") or 0)
        seconds = float(stats.get("upload_seconds") or 0) + float(
            stats.get("download_seconds") or 0
        )
        return {
            "upload_bytes": upload_bytes,
            "download_bytes": download_bytes,
            "upload_seconds": round(float(stats.get("upload_seconds") or 0), 3),
            "download_seconds": round(float(stats.get("download_seconds") or 0), 3),
            "dedup_uploads": int(stats.get("upload_dedup") or 0),
            "mb_per_sec": round(
                (upload_bytes + download_bytes) / 1_000_000 / max(seconds, 0.001), 3
            ),
        }

    def submit(
        self,
        capability: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """Submit a capability job, wait, and fetch its artifacts.

        Shared mount is preferred when configured, but a failed or empty shared
        output falls back to HTTP automatically. The result always reports the
        transport and whether the job was degraded.
        """

        body = dict(payload or {})
        started_at = now_iso()
        started = time.perf_counter()
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
        raw_inputs = [str(item) for item in body.get("inputs", []) or []]
        if not raw_inputs and body.get("input"):
            raw_inputs = [str(body["input"])]
        shared_inputs = [str(item) for item in body.get("shared_inputs", []) or []]
        shared_outputs = [str(item) for item in body.get("shared_outputs", []) or []]
        body_shared_root = str(body.get("shared_root") or "") or ""
        shared_root = body_shared_root
        shared_local_root = str(
            body.get("shared_local_root") or self.shared_local_root or ""
        )
        health = self._health
        if not shared_root and health is not None and health.shared_root:
            shared_root = str(health.shared_root)
        transport_reason = ""
        shared_mode = (
            self.transport in {"auto", "shared"}
            and bool(shared_root and shared_local_root)
        )
        upload_raw = raw_inputs
        if shared_mode:
            upload_raw = []
            mapped: list[str] = []
            for item in raw_inputs:
                relative = _shared_relative(shared_local_root, item)
                if relative:
                    mapped.append(relative)
                else:
                    upload_raw.append(item)
            for relative in mapped:
                if relative not in shared_inputs:
                    shared_inputs.append(relative)
        elif self.transport == "shared":
            transport_reason = (
                "shared transport requested but VF_GPU_SHARED_LOCAL_ROOT or the "
                "worker shared root is missing; used HTTP"
            )
        reset_transfer = getattr(self.client, "reset_transfer_stats", None)
        if callable(reset_transfer):
            reset_transfer()
        inputs = self._prepare_remote_inputs(upload_raw)
        shared_placeholders: dict[str, str] = {}
        if shared_mode:
            base = len(inputs)
            for index, relative in enumerate(shared_inputs):
                try:
                    local = (Path(shared_local_root) / relative).resolve()
                except (OSError, ValueError):
                    continue
                shared_placeholders[str(local)] = f"__VF_INPUT_{base + index}__"
        params = self._prepare_remote_params(params, inputs, shared_placeholders)
        share_remote_root = shared_root if (shared_mode or body_shared_root) else ""
        submit_kwargs: dict[str, Any] = {
            "params": params,
            "inputs": inputs,
            "shared_inputs": shared_inputs if share_remote_root else [],
            "shared_outputs": shared_outputs,
            "shared_root": share_remote_root or None,
        }
        try:
            job_id = self.client.submit(
                capability,
                priority=int(body.get("priority") or 0),
                **submit_kwargs,
            )
        except TypeError:
            # Older workers and test doubles do not accept the priority keyword.
            job_id = self.client.submit(capability, **submit_kwargs)
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

        degraded = bool(transport_reason)
        degraded_reason = transport_reason
        if (
            shared_root
            and status.shared_artifacts
            and len(status.shared_artifacts) == len(shared_outputs)
        ):
            shared_paths = [
                Path(shared_root) / relative
                for relative in status.shared_artifacts
            ]
            if all(_valid_shared_file(path) for path in shared_paths):
                elapsed = time.perf_counter() - started
                execution = ExecutionRecord(
                    run_id=job_id,
                    capability=capability,
                    execution_node=decision.execution_node,
                    device="remote_gpu",
                    degraded=False,
                    started_at=started_at,
                    finished_at=now_iso(),
                    elapsed_sec=elapsed,
                )
                return {
                    "path": str(shared_paths[0]),
                    "paths": [str(path) for path in shared_paths],
                    "job_id": job_id,
                    "execution_node": decision.execution_node,
                    "artifacts": list(status.artifacts),
                    "shared_artifacts": list(status.shared_artifacts),
                    "shared_inputs": list(shared_inputs),
                    "transport": "shared_mount",
                    "transfer": self._transfer_summary(),
                    "degraded": bool(transport_reason),
                    "degraded_reason": transport_reason,
                    "execution": execution.to_dict(),
                }
            degraded = True
            degraded_reason = "shared artifact missing or empty; downloaded over HTTP"
        elif shared_root and shared_outputs:
            degraded = True
            degraded_reason = status.shared_error or "shared output was not produced"
        elif status.shared_error:
            degraded = True
            degraded_reason = status.shared_error

        manifest: list[dict[str, Any]] = []
        manifest_reader = getattr(self.client, "artifact_manifest", None)
        if callable(manifest_reader):
            try:
                manifest = manifest_reader(job_id)
            except Exception:  # noqa: BLE001 - manifest is an optimization
                manifest = []
        target_dir = Path(tempfile.mkdtemp(prefix="vf-remote-"))
        download_all = getattr(self.client, "download_all", None)
        if callable(download_all):
            paths = download_all(
                job_id,
                list(status.artifacts),
                target_dir,
                manifest=manifest,
            )
        else:
            name = status.artifacts[0]
            paths = [self.client.download(job_id, name, target_dir / Path(name).name)]
        elapsed = time.perf_counter() - started
        execution = ExecutionRecord(
            run_id=job_id,
            capability=capability,
            execution_node=decision.execution_node,
            device="remote_gpu",
            degraded=degraded,
            degraded_reason=degraded_reason,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=elapsed,
        )
        return {
            "path": str(paths[0]),
            "paths": [str(path) for path in paths],
            "job_id": job_id,
            "execution_node": decision.execution_node,
            "artifacts": list(status.artifacts),
            "shared_artifacts": list(status.shared_artifacts),
            "shared_inputs": list(shared_inputs),
            "transport": "http_fallback" if degraded else "http",
            "transfer": self._transfer_summary(),
            "degraded": degraded,
            "degraded_reason": degraded_reason,
            "execution": execution.to_dict(),
        }


__all__ = ["COMPUTE_MODES", "ComputeRouter"]
