"""Compute placement contracts and GPU worker client for VideoFlow."""

from __future__ import annotations

from vf_compute.capabilities import CAPABILITIES, VRAM_COST_MB, vram_cost
from vf_compute.client import GPUWorkerClient, GPUWorkerError
from vf_compute.discovery import DiscoveredWorker, GpuDiscovery, discover_workers
from vf_compute.models import JobStatus, WorkerDecision, WorkerHealth
from vf_compute.router import COMPUTE_MODES, ComputeRouter

__all__ = [
    "CAPABILITIES",
    "COMPUTE_MODES",
    "ComputeRouter",
    "DiscoveredWorker",
    "GPUWorkerClient",
    "GPUWorkerError",
    "GpuDiscovery",
    "JobStatus",
    "VRAM_COST_MB",
    "WorkerDecision",
    "WorkerHealth",
    "discover_workers",
    "vram_cost",
]
