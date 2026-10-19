"""Decide which rack modules a run will execute. This does not execute them."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from videoflow.domain.constants import MODULE_ORDER
from videoflow.domain.errors import (
    JobAlreadyRunningError,
    ModuleBypassedError,
    UpstreamDirtyError,
    VideoFlowError,
)


class CacheStatus(StrEnum):
    CACHED = "cached"
    DIRTY = "dirty"
    MISSING = "missing"
    BYPASSED = "bypassed"
    FAILED = "failed"
    BLOCKED = "blocked"
    RUNNING = "running"


_NEEDS_WORK = {
    CacheStatus.DIRTY,
    CacheStatus.MISSING,
    CacheStatus.FAILED,
    CacheStatus.BLOCKED,
}


class UnknownModuleError(VideoFlowError):
    code = "unknown_module"

    def __init__(self, module: str) -> None:
        self.module = module
        super().__init__(f"Unknown module: {module}")


@dataclass(frozen=True, slots=True)
class RunPlan:
    modules: tuple[str, ...]
    skipped: tuple[str, ...]


def plan_run(
    status: Mapping[str, CacheStatus | str],
    *,
    target: str | None = None,
    run_upstream: bool = False,
    enabled: Mapping[str, bool] | None = None,
) -> RunPlan:
    """Plan a full rack run, or a single module.

    A cached or bypassed module is skipped. A single-module run refuses to
    start when an earlier enabled module is dirty, missing, failed, or blocked,
    unless ``run_upstream`` is set. ``RUNNING`` anywhere means a job already
    owns the project.
    """

    normalized = _normalize(status)
    _reject_if_running(normalized)
    if target is None:
        return _plan_all(normalized, enabled)
    _require_known(target)
    if enabled is not None and not enabled.get(target, True):
        raise ModuleBypassedError(target)
    if normalized[target] is CacheStatus.BYPASSED:
        raise ModuleBypassedError(target)
    ancestors = _ancestors(target, normalized, enabled)
    blocking = [name for name in ancestors if normalized[name] in _NEEDS_WORK]
    if blocking and not run_upstream:
        raise UpstreamDirtyError(target, blocking)
    if normalized[target] is CacheStatus.CACHED and not blocking:
        return RunPlan(modules=(), skipped=(target,))
    modules: list[str] = []
    skipped: list[str] = []
    for name in (*ancestors, target):
        if normalized[name] in (CacheStatus.CACHED, CacheStatus.BYPASSED):
            skipped.append(name)
            continue
        modules.append(name)
    return RunPlan(modules=tuple(modules), skipped=tuple(skipped))


def _plan_all(
    status: Mapping[str, CacheStatus],
    enabled: Mapping[str, bool] | None,
) -> RunPlan:
    modules: list[str] = []
    skipped: list[str] = []
    for name in MODULE_ORDER:
        if enabled is not None and not enabled.get(name, True):
            skipped.append(name)
            continue
        current = status[name]
        if current in (CacheStatus.CACHED, CacheStatus.BYPASSED):
            skipped.append(name)
            continue
        modules.append(name)
    return RunPlan(modules=tuple(modules), skipped=tuple(skipped))


def _ancestors(
    target: str,
    status: Mapping[str, CacheStatus],
    enabled: Mapping[str, bool] | None,
) -> tuple[str, ...]:
    names: list[str] = []
    for name in MODULE_ORDER:
        if name == target:
            break
        if enabled is not None and not enabled.get(name, True):
            continue
        if status[name] is CacheStatus.BYPASSED:
            continue
        names.append(name)
    return tuple(names)


def _normalize(status: Mapping[str, CacheStatus | str]) -> dict[str, CacheStatus]:
    normalized: dict[str, CacheStatus] = {}
    for name in MODULE_ORDER:
        raw = status.get(name, CacheStatus.MISSING)
        normalized[name] = raw if isinstance(raw, CacheStatus) else CacheStatus(raw)
    return normalized


def _reject_if_running(status: Mapping[str, CacheStatus]) -> None:
    for name, current in status.items():
        if current is CacheStatus.RUNNING:
            raise JobAlreadyRunningError(name)


def _require_known(module: str) -> None:
    if module not in MODULE_ORDER:
        raise UnknownModuleError(module)
