"""Direct FFmpeg render for shorts and previews. Never the editing master."""

from __future__ import annotations

from pathlib import Path

from videoflow.domain.state import ProjectState


def export_mp4(state: ProjectState, output_path: Path) -> Path:
    """Render a preview or short. Not implemented in the scaffold."""

    raise NotImplementedError("MP4 render is specified but not implemented in this scaffold")
