"""Health probes and remote placement decisions for the compute router."""

from __future__ import annotations

import time

from vf_shared.compute.capabilities import vram_cost
from vf_shared.compute.models import WorkerDecision, WorkerHealth

from .router_common import _DISCOVERY_TTL, _local


class RouterHealthMixin:
    """Worker health, circuit breaker and placement decisions."""

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
        if (
            self.max_gpu_utilization > 0
            and health.gpu_utilization > self.max_gpu_utilization
        ):
            return (
                "external GPU load above cap: "
                f"{health.gpu_utilization:.0f}% > "
                f"{self.max_gpu_utilization:.0f}%"
            )
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
