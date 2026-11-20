"""Shared readers for Short plan, manifest, cues, and export artifacts.

The Short steps used to repeat the same metadata-then-artifact fallback. Every
lookup now goes through this module so precedence and error messages stay
consistent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.scene_intel.io import read_json
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ShortPlanError, StateNotReadyError
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.short_composition import ShortCompositionPlan


def read_optional_plan(
    context: PipelineContext,
    override: str = "",
) -> dict[str, Any]:
    """Return the raw plan from an override, metadata, or artifact."""

    if override:
        raw = read_json(Path(override).expanduser())
        if raw:
            return raw
    metadata = context.metadata.get("short_plan")
    if isinstance(metadata, dict) and metadata:
        return metadata
    artifact = context.artifacts.get("short_plan", "")
    return read_json(Path(artifact)) if artifact else {}


def read_plan(
    context: PipelineContext,
    override: str = "",
    *,
    step: str = "short.plan",
    error_cls: type[Exception] = ShortPlanError,
    error_prefix: str = "Invalid Short plan",
) -> ShortCompositionPlan:
    raw = read_optional_plan(context, override)
    if not raw:
        raise StateNotReadyError(f"Run short.plan before {step}")
    try:
        return ShortCompositionPlan.model_validate(raw)
    except ValueError as exc:
        raise error_cls(f"{error_prefix}: {exc}") from exc


def read_manifest(
    context: PipelineContext,
    *,
    step: str,
    error_cls: type[Exception] = ShortPlanError,
    error_prefix: str = "Invalid scene manifest",
    missing_error: type[Exception] = StateNotReadyError,
) -> ScenesManifest:
    raw = context.metadata.get("scenes_manifest")
    if not isinstance(raw, dict) or not raw:
        artifact = context.artifacts.get("scenes_manifest", "")
        raw = read_json(Path(artifact)) if artifact else {}
    if not raw:
        raise missing_error(f"Run scene.analyze before {step}")
    try:
        return ScenesManifest.model_validate(raw)
    except ValueError as exc:
        raise error_cls(f"{error_prefix}: {exc}") from exc


def read_supercontext(context: PipelineContext) -> dict[str, Any]:
    metadata = context.metadata.get("scenes_supercontext")
    if isinstance(metadata, dict) and metadata:
        return metadata
    artifact = context.artifacts.get("scenes_supercontext", "")
    return read_json(Path(artifact)) if artifact else {}


def read_cues(context: PipelineContext, override: str = "") -> dict[str, Any]:
    if override:
        raw = read_json(Path(override).expanduser())
        if raw:
            return raw
    metadata = context.metadata.get("short_cues")
    if isinstance(metadata, dict) and metadata:
        return metadata
    artifact = context.artifacts.get("short_cues", "")
    return read_json(Path(artifact)) if artifact else {}


def read_export_report(context: PipelineContext, override: str = "") -> dict[str, Any]:
    if override:
        path = Path(override).expanduser()
        raw = read_json(path) if path.is_file() else {}
        if raw:
            return raw
    artifact = context.artifacts.get("short_export_report", "")
    path = Path(artifact) if artifact else None
    raw = read_json(path) if path is not None and path.is_file() else {}
    if raw:
        return raw
    metadata = context.metadata.get("short_export")
    return metadata if isinstance(metadata, dict) else {}


__all__ = [
    "read_cues",
    "read_export_report",
    "read_manifest",
    "read_optional_plan",
    "read_plan",
    "read_supercontext",
]
