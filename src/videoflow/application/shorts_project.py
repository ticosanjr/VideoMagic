"""Read and write the persisted state of a completed Shorts project."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from videoflow.domain.errors import ShortEditError, StateNotReadyError
from videoflow.domain.state import ProjectState


def load_short_project(output: Path) -> tuple[ProjectState, dict[str, Any]]:
    """Load ``project_state.json`` and ``shorts.json`` for a Shorts project."""

    output = output.expanduser().resolve()
    try:
        state = ProjectState.model_validate_json(
            (output / "project_state.json").read_text(encoding="utf-8")
        )
        report = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateNotReadyError(
            f"Cannot read the completed Shorts project: {exc}"
        ) from exc
    if not isinstance(report, dict):
        raise StateNotReadyError("Cannot read the completed Shorts project: invalid report.")
    return state, report


def short_entry(
    container: dict[str, Any],
    index: int,
    *,
    key: str = "shorts",
) -> dict[str, Any]:
    """Return one clip entry from a result/report container."""

    items = container.get(key)
    if not isinstance(items, list) or index < 0 or index >= len(items):
        raise ShortEditError(f"Short index {index} is out of range.")
    entry = items[index]
    if not isinstance(entry, dict):
        raise ShortEditError(f"Short index {index} is invalid.")
    return entry


def short_pieces(
    entry: dict[str, Any],
    *,
    require: bool = True,
    strict: bool = True,
) -> list[tuple[int, int]]:
    """Parse the source sample ranges of a clip entry."""

    raw_pieces = entry.get("pieces") or []
    if strict:
        try:
            pieces = [(int(piece[0]), int(piece[1])) for piece in raw_pieces]
        except (TypeError, ValueError, IndexError) as exc:
            raise ShortEditError("The Short pieces are invalid.") from exc
    else:
        pieces = [
            (int(piece[0]), int(piece[1]))
            for piece in raw_pieces
            if isinstance(piece, (list, tuple)) and len(piece) == 2
        ]
    if require and not pieces:
        raise ShortEditError("The Short has no source pieces.")
    return pieces


def transcript_text(state: ProjectState, pieces: Sequence[tuple[int, int]]) -> str:
    """Join the transcript sentences that overlap the clip's source pieces."""

    return " ".join(
        sentence.text
        for sentence in state.transcript
        if any(
            sentence.end_sample > start and sentence.start_sample < end
            for start, end in pieces
        )
    )


def save_short_entry(
    output: Path,
    report: dict[str, Any],
    index: int,
    entry: dict[str, Any],
    *,
    fallback: Sequence[Any],
) -> None:
    """Replace one clip entry in ``shorts.json`` and persist the report."""

    clips = report.get("clips")
    if isinstance(clips, list) and 0 <= index < len(clips):
        clips[index] = entry
    payload = clips if isinstance(clips, list) else list(fallback)
    (output.expanduser().resolve() / "shorts.json").write_text(
        json.dumps({"ok": True, "clips": payload}, indent=2) + "\n",
        encoding="utf-8",
    )
