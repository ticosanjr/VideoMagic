"""Compute placement contracts and GPU worker client for VideoFlow."""

from __future__ import annotations

from vf_compute.capabilities import CAPABILITIES, VRAM_COST_MB, vram_cost
from vf_compute.client import GPUWorkerClient, GPUWorkerError
from vf_compute.config import (
    GpuConfig,
    clear_gpu_config,
    config_path,
    load_gpu_config,
    save_gpu_config,
)
from vf_compute.discovery import DiscoveredWorker, GpuDiscovery, discover_workers
from vf_compute.execution import ExecutionRecord, now_iso
from vf_compute.models import JobStatus, WorkerDecision, WorkerHealth
from vf_compute.router import COMPUTE_MODES, ComputeRouter

__all__ = [
    "CAPABILITIES",
    "COMPUTE_MODES",
    "ComputeRouter",
    "DiscoveredWorker",
    "ExecutionRecord",
    "GPUWorkerClient",
    "GPUWorkerError",
    "GpuConfig",
    "GpuDiscovery",
    "JobStatus",
    "clear_gpu_config",
    "config_path",
    "load_gpu_config",
    "save_gpu_config",
    "VRAM_COST_MB",
    "WorkerDecision",
    "WorkerHealth",
    "discover_workers",
    "now_iso",
    "vram_cost",
]
