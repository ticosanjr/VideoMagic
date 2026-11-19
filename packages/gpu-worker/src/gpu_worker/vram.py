"""VRAM budget and GPU telemetry for the worker."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gpu_worker.models import ModelRegistry


@dataclass(frozen=True, slots=True)
class GpuMemory:
    available: bool
    free_mb: int = 0
    total_mb: int = 0
    used_mb: int = 0
    utilization: float = 0.0
    temperature_c: float = 0.0


CPU_MEMORY = GpuMemory(available=False)


class VramError(RuntimeError):
    """Raised when a job cannot fit in the configured VRAM budget."""


def read_gpu_memory() -> GpuMemory:
    """Read memory/utilization/temperature from ``nvidia-smi``."""

    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.free,memory.total,memory.used,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return CPU_MEMORY
    if completed.returncode != 0:
        return CPU_MEMORY
    line = next((item.strip() for item in completed.stdout.splitlines() if item.strip()), "")
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 3:
        return CPU_MEMORY
    try:
        free, total, used = (int(float(parts[index])) for index in range(3))
    except ValueError:
        return CPU_MEMORY
    utilization = 0.0
    temperature = 0.0
    if len(parts) > 3:
        try:
            utilization = float(parts[3])
        except ValueError:
            utilization = 0.0
    if len(parts) > 4:
        try:
            temperature = float(parts[4])
        except ValueError:
            temperature = 0.0
    return GpuMemory(
        available=True,
        free_mb=max(free, 0),
        total_mb=max(total, 0),
        used_mb=max(used, 0),
        utilization=max(utilization, 0.0),
        temperature_c=max(temperature, 0.0),
    )


class VramBudget:
    """Enforce a configured VRAM budget and evict LRU models when needed."""

    def __init__(
        self,
        *,
        max_vram_mb: int = 10_240,
        reserve_mb: int = 512,
        ttl_sec: float = 2.0,
        reader=read_gpu_memory,
    ) -> None:
        self.max_vram_mb = max(int(max_vram_mb), 0)
        self.reserve_mb = max(int(reserve_mb), 0)
        self.ttl_sec = max(float(ttl_sec), 0.0)
        self._reader = reader
        self._info = CPU_MEMORY
        self._read_at = 0.0
        self._lock = threading.RLock()

    def info(self, *, force: bool = False) -> GpuMemory:
        with self._lock:
            now = time.monotonic()
            if force or now - self._read_at >= self.ttl_sec:
                self._info = self._reader()
                self._read_at = now
            return self._info

    def budget_mb(self) -> int:
        info = self.info()
        if self.max_vram_mb:
            return min(self.max_vram_mb, info.total_mb or self.max_vram_mb)
        return info.total_mb

    def ensure(self, required_mb: int, models: ModelRegistry) -> list[str]:
        """Ensure ``required_mb`` fits, evicting least-recently-used models.

        CPU-only workers have no VRAM reading and are never blocked here.
        """

        required = max(int(required_mb), 0)
        if required <= 0:
            return []
        info = self.info(force=True)
        if not info.available:
            return []
        budget = self.budget_mb() or info.free_mb
        free = min(info.free_mb, budget)
        if required + self.reserve_mb <= free:
            return []
        names, freed = models.unload_lru(required + self.reserve_mb - free)
        if required + self.reserve_mb <= free + freed:
            return names
        raise VramError(
            "insufficient VRAM: "
            f"need {required + self.reserve_mb} MB including reserve, "
            f"free {free + freed} MB, budget {budget} MB"
        )


__all__ = ["CPU_MEMORY", "GpuMemory", "VramBudget", "VramError", "read_gpu_memory"]
