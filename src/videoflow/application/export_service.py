"""One timeline, three NLE artifacts. The API and MCP call this service."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState
from videoflow.exporters.fcpxml import Dialect, export_fcpxml
from videoflow.exporters.kdenlive import export_kdenlive
from videoflow.exporters.xmeml import export_xmeml

Target = Literal["resolve", "premiere", "kdenlive"]
DEFAULT_TARGETS: tuple[Target, ...] = ("resolve", "premiere", "kdenlive")

FILENAMES: dict[str, str] = {
    "resolve": "timeline.fcpxml",
    "premiere": "timeline.xml",
    "kdenlive": "timeline.kdenlive",
}


def export_timeline(
    state: ProjectState,
    output_dir: Path,
    *,
    targets: Sequence[str] = DEFAULT_TARGETS,
    dialect: Dialect = "1.9",
) -> dict[str, Path]:
    """Write every requested artifact from the same validated timeline."""

    directory = Path(output_dir).expanduser()
    artifacts: dict[str, Path] = {}
    for target in targets:
        if target not in FILENAMES:
            raise ExportError(f"Unknown export target: {target}")
        destination = directory / FILENAMES[target]
        if target == "resolve":
            artifacts[target] = export_fcpxml(state, destination, dialect=dialect)
        elif target == "premiere":
            artifacts[target] = export_xmeml(state, destination)
        else:
            artifacts[target] = export_kdenlive(state, destination)
    return artifacts
