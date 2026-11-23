"""Compute placement contracts and GPU worker client for VideoFlow."""

from __future__ import annotations

from vf_shared.compute.capabilities import (
    CAPABILITIES,
    HEAVY_CAPABILITIES,
    VRAM_COST_MB,
    canonical_capability,
    is_heavy_capability,
    vram_cost,
)
from vf_shared.compute.client import (
    GPUWorkerAuthError,
    GPUWorkerClient,
    GPUWorkerError,
)
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
from vf_shared.compute.local_gpu import (
    cuda_device_count,
    local_gpu_available,
    reset_local_gpu_cache,
)
from vf_shared.compute.models import JobStatus, WorkerDecision, WorkerHealth
from vf_shared.compute.router import COMPUTE_MODES, ComputeRouter

__all__ = [
    "CAPABILITIES",
    "COMPUTE_MODES",
    "ComputeRouter",
    "DiscoveredWorker",
    "ExecutionRecord",
    "GPUWorkerAuthError",
    "GPUWorkerClient",
    "GPUWorkerError",
    "GpuConfig",
    "GpuDiscovery",
    "HEAVY_CAPABILITIES",
    "JobStatus",
    "canonical_capability",
    "clear_gpu_config",
    "config_path",
    "cuda_device_count",
    "env_worker_url",
    "is_heavy_capability",
    "load_gpu_config",
    "load_gpu_config_file",
    "local_gpu_available",
    "reset_local_gpu_cache",
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
