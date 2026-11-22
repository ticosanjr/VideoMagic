"""Compute placement contracts and GPU worker client for VideoFlow."""

from __future__ import annotations

from vf_shared.compute.capabilities import CAPABILITIES, VRAM_COST_MB, vram_cost
from vf_shared.compute.client import GPUWorkerClient, GPUWorkerError
from vf_shared.compute.config import (
    GpuConfig,
    clear_gpu_config,
    config_path,
    env_worker_url,
    load_gpu_config,
    load_gpu_config_file,
    save_gpu_config,
)
from vf_shared.compute.discovery import (
    DiscoveredWorker,
    GpuDiscovery,
    discover_workers,
    scan_workers,
)
from vf_shared.compute.errors import WorkerOfflineError
from vf_shared.compute.execution import ExecutionRecord, now_iso
from vf_shared.compute.models import JobStatus, WorkerDecision, WorkerHealth
from vf_shared.compute.router import COMPUTE_MODES, ComputeRouter

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
    "env_worker_url",
    "load_gpu_config",
    "load_gpu_config_file",
    "save_gpu_config",
    "VRAM_COST_MB",
    "WorkerDecision",
    "WorkerHealth",
    "WorkerOfflineError",
    "discover_workers",
    "scan_workers",
    "now_iso",
    "vram_cost",
]
