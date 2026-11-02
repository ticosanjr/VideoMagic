"""One timeline to NLE documents or a direct MP4. The API and MCP call this service."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from videoflow import plugin_api
from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState
from videoflow.exporters.extras import EMPTY, NleExtras
from videoflow.exporters.fcpxml import Dialect, export_fcpxml
from videoflow.exporters.kdenlive import export_kdenlive
from videoflow.exporters.mp4 import export_mp4
from videoflow.exporters.xmeml import export_xmeml

Target = Literal["resolve", "premiere", "kdenlive", "mp4"]
DEFAULT_TARGETS: tuple[Target, ...] = ("resolve", "premiere", "kdenlive")

FILENAMES: dict[str, str] = {
    "resolve": "timeline.fcpxml",
    "premiere": "timeline.xml",
    "kdenlive": "timeline.kdenlive",
    "mp4": "timeline.mp4",
}


def export_timeline(
    state: ProjectState,
    output_dir: Path,
    *,
    targets: Sequence[str] = DEFAULT_TARGETS,
    dialect: Dialect = "1.9",
    extras: NleExtras = EMPTY,
    progress: Callable[[str, int], None] | None = None,
    should_cancel: Callable[[], object] | None = None,
    adapter: Any | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Path]:
    """Write every requested artifact from the same validated timeline."""

    directory = Path(output_dir).expanduser()
    artifacts: dict[str, Path] = {}
    ordered = [target for target in targets if target != "mp4"] + [
        target for target in targets if target == "mp4"
    ]
    for target in ordered:
        if should_cancel is not None and should_cancel():
            from videoflow.domain.errors import JobCancelledError

            raise JobCancelledError("Cancelled")
        if progress is not None:
            progress(target, 0)
        if target not in FILENAMES:
            handler = plugin_api.exporter(target)
            if handler is None:
                raise ExportError(f"Unknown export target: {target}")
            artifacts[target] = Path(handler(state, directory))
            if progress is not None:
                progress(target, 100)
            continue
        destination = directory / FILENAMES[target]
        if target == "resolve":
            artifacts[target] = export_fcpxml(
                state, destination, dialect=dialect, extras=extras
            )
        elif target == "premiere":
            artifacts[target] = export_xmeml(state, destination, extras=extras)
        elif target == "kdenlive":
            artifacts[target] = export_kdenlive(state, destination, extras=extras)
        else:
            artifacts[target] = export_mp4(
                state,
                destination,
                adapter=adapter,
                progress=(
                    (lambda value, name=target: progress(name, value))
                    if progress
                    else None
                ),
                cache_dir=cache_dir,
            )
        if progress is not None:
            progress(target, 100)
    return artifacts
