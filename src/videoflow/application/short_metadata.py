"""Generate and persist social metadata for one completed Short."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.metadata import generate_metadata
from videoflow.application.shorts_project import (
    load_short_project,
    save_short_entry,
    short_entry,
    short_pieces,
    transcript_text,
)
from videoflow.domain.errors import ShortEditError


def generate_short_metadata(
    *,
    output: Path,
    index: int,
    result: dict[str, Any],
    platform: str = "youtube",
    tone: str = "engaging",
    extra_hashtags: tuple[str, ...] = (),
) -> dict[str, object]:
    entry = short_entry(result, index)
    state, report = load_short_project(output)
    pieces = short_pieces(entry)
    text = transcript_text(state, pieces)
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
    save_short_entry(
        output,
        report,
        index,
        entry,
        fallback=result.get("shorts") or [],
    )
    return payload
