"""Resolve recipe-level source and workspace defaults from node configuration."""

from __future__ import annotations

from pathlib import Path

from videoflow.domain.errors import RecipeError
from videoflow.domain.paths import resolve_allowed


def resolve_run_roots(
    recipe,
    source: str | None,
    output: str | None,
    roots: list[Path],
) -> tuple[Path, Path]:
    source_value = (source or "").strip()
    if not source_value:
        for step in recipe.enabled_steps():
            configured = str(step.params.get("source") or "").strip()
            if configured:
                source_value = configured
                break
            if step.media_override.strip():
                source_value = step.media_override.strip()
                break
    output_value = (output or "").strip()
    if not source_value:
        if any(step.type == "ingest" for step in recipe.enabled_steps()):
            raise RecipeError(
                "No input media. Set a source on the ingest node in the recipe."
            )
        # Script-first recipes have no source media. Keep a deterministic
        # placeholder under the workspace so the runner and cache stay happy.
        if output_value:
            resolved_output = resolve_allowed(Path(output_value), roots)
        else:
            base = roots[0] if roots else Path.home()
            resolved_output = resolve_allowed(
                base / "VideoFlow" / recipe.id, roots
            )
        return resolved_output / ".script-source", resolved_output
    resolved_source = resolve_allowed(Path(source_value), roots)
    if output_value:
        resolved_output = resolve_allowed(Path(output_value), roots)
    else:
        resolved_output = resolve_allowed(
            resolved_source.with_name(f"{resolved_source.stem}-videoflow"), roots
        )
    return resolved_source, resolved_output
