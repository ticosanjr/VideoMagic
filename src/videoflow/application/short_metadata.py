"""Generate and persist social metadata for one completed Short."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.application.metadata import generate_metadata
from videoflow.domain.errors import ShortEditError, StateNotReadyError
from videoflow.domain.state import ProjectState


def generate_short_metadata(
    *,
    output: Path,
    index: int,
    result: dict[str, Any],
    platform: str = "youtube",
    tone: str = "engaging",
    extra_hashtags: tuple[str, ...] = (),
) -> dict[str, object]:
    shorts = result.get("shorts")
    if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
        raise ShortEditError(f"Short index {index} is out of range.")
    entry = shorts[index]
    if not isinstance(entry, dict):
        raise ShortEditError(f"Short index {index} is invalid.")
    output = output.expanduser().resolve()
    state_path = output / "project_state.json"
    shorts_path = output / "shorts.json"
    try:
        state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        report = json.loads(shorts_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateNotReadyError(
            f"Cannot read the completed Shorts project: {exc}"
        ) from exc
    raw_pieces = entry.get("pieces") or []
    try:
        pieces = [(int(piece[0]), int(piece[1])) for piece in raw_pieces]
    except (TypeError, ValueError, IndexError) as exc:
        raise ShortEditError("The Short pieces are invalid.") from exc
    if not pieces:
        raise ShortEditError("The Short has no source pieces.")
    text = " ".join(
        sentence.text
        for sentence in state.transcript
        if any(
            sentence.end_sample > start and sentence.start_sample < end
            for start, end in pieces
        )
    )
    try:
        metadata = generate_metadata(
            text,
            title=str(entry.get("title") or ""),
            platform=platform,
            tone=tone,
            extra_hashtags=extra_hashtags,
        )
    except ValueError as exc:
        raise ShortEditError(str(exc)) from exc
    payload = metadata.to_dict()
    metadata_map = entry.get("metadata")
    if not isinstance(metadata_map, dict):
        metadata_map = {}
    metadata_map[str(payload["platform"])] = payload
    entry["metadata"] = metadata_map
    clips = report.get("clips")
    if isinstance(clips, list) and 0 <= index < len(clips):
        clips[index] = entry
    shorts_path.write_text(
        json.dumps(
            {"ok": True, "clips": clips if isinstance(clips, list) else shorts},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return payload
