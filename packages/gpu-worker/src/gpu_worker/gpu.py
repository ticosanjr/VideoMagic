"""Best-effort GPU detection through ``nvidia-smi``."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GpuInfo:
    available: bool
    name: str
    vram_free_mb: int
    vram_total_mb: int


CPU_ONLY = GpuInfo(available=False, name="cpu", vram_free_mb=0, vram_total_mb=0)


def detect_gpu() -> GpuInfo:
    """Query the first NVIDIA GPU, falling back to CPU-only information."""

    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.free,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return CPU_ONLY
    if completed.returncode != 0:
        return CPU_ONLY

    line = next((item.strip() for item in completed.stdout.splitlines() if item.strip()), "")
    if not line:
        return CPU_ONLY
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 3:
        return GpuInfo(available=True, name=parts[0] or "unknown", vram_free_mb=0, vram_total_mb=0)
    try:
        free = int(float(parts[1]))
        total = int(float(parts[2]))
    except ValueError:
        free = total = 0
    return GpuInfo(
        available=True,
        name=parts[0] or "unknown",
        vram_free_mb=max(free, 0),
        vram_total_mb=max(total, 0),
    )
