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
    vram_used_mb: int = 0
    gpu_utilization: float = 0.0
    temperature_c: float = 0.0
    driver_version: str = ""


CPU_ONLY = GpuInfo(available=False, name="cpu", vram_free_mb=0, vram_total_mb=0)


def detect_gpu() -> GpuInfo:
    """Query the first NVIDIA GPU, falling back to CPU-only information."""

    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.free,memory.total,memory.used,utilization.gpu,temperature.gpu",
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
    if len(parts) < 4:
        return GpuInfo(
            available=True,
            name=parts[0] or "unknown",
            vram_free_mb=0,
            vram_total_mb=0,
            driver_version=parts[1] if len(parts) > 1 else "",
        )
    driver = parts[1]
    try:
        free = int(float(parts[2]))
        total = int(float(parts[3]))
    except ValueError:
        free = total = 0
    used = 0
    utilization = 0.0
    temperature = 0.0
    if len(parts) > 4:
        try:
            used = int(float(parts[4]))
        except ValueError:
            used = 0
    if len(parts) > 5:
        try:
            utilization = float(parts[5])
        except ValueError:
            utilization = 0.0
    if len(parts) > 6:
        try:
            temperature = float(parts[6])
        except ValueError:
            temperature = 0.0
    return GpuInfo(
        available=True,
        name=parts[0] or "unknown",
        vram_free_mb=max(free, 0),
        vram_total_mb=max(total, 0),
        vram_used_mb=max(used, 0),
        gpu_utilization=max(utilization, 0.0),
        temperature_c=max(temperature, 0.0),
        driver_version=driver,
    )
