from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "packages" / "gpu-worker" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from gpu_worker.models import ModelRegistry  # noqa: E402
from gpu_worker.vram import GpuMemory, VramBudget, VramError  # noqa: E402


def test_model_registry_tracks_vram_and_unloads_lru() -> None:
    registry = ModelRegistry(ttl_seconds=0)
    registry.register("old", vram_mb=2000)
    registry.register("new", vram_mb=1500)
    registry.touch("old")
    names, freed = registry.unload_lru(1500)
    assert names == ["new"]
    assert freed == 1500
    assert registry.vram_used_mb() == 2000


def test_vram_budget_evicts_until_the_job_fits() -> None:
    registry = ModelRegistry(ttl_seconds=0)
    registry.register("a", vram_mb=2000)
    registry.register("b", vram_mb=2000)
    budget = VramBudget(
        max_vram_mb=4096,
        reserve_mb=0,
        reader=lambda: GpuMemory(available=True, free_mb=1000, total_mb=8192),
    )
    names = budget.ensure(2500, registry)
    assert names == ["a"]
    assert registry.vram_used_mb() == 2000


def test_vram_budget_rejects_jobs_that_cannot_fit() -> None:
    registry = ModelRegistry(ttl_seconds=0)
    budget = VramBudget(
        max_vram_mb=2048,
        reserve_mb=0,
        reader=lambda: GpuMemory(available=True, free_mb=0, total_mb=2048),
    )
    with pytest.raises(VramError, match="insufficient VRAM"):
        budget.ensure(3000, registry)


def test_vram_budget_is_permissive_on_cpu_only_workers() -> None:
    registry = ModelRegistry(ttl_seconds=0)
    budget = VramBudget(
        max_vram_mb=2048,
        reader=lambda: GpuMemory(available=False),
    )
    assert budget.ensure(99999, registry) == []
    assert budget.info().available is False


def test_vram_budget_respects_the_configured_cap() -> None:
    budget = VramBudget(
        max_vram_mb=6000,
        reader=lambda: GpuMemory(available=True, free_mb=8000, total_mb=12288),
    )
    assert budget.budget_mb() == 6000
