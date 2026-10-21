"""Re-render one selected Short from the source pieces."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.shorts import (
    build_ass,
    build_ass_lines,
    caption_lines,
    sentence_events,
    short_dimensions,
    slice_pieces,
    slugify,
)
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import ShortEditError, StateNotReadyError
from videoflow.domain.state import ProjectState


@dataclass(frozen=True, slots=True)
class ShortEditOptions:
    title: str | None = None
    start_sec: float | None = None
    end_sec: float | None = None
    aspect_ratio: str | None = None
    burn_subtitles: bool | None = None
    caption_style: dict[str, Any] | None = None


def edit_short(
    *,
    source: Path,
    output: Path,
    index: int,
    result: dict[str, Any],
    options: ShortEditOptions,
) -> dict[str, Any]:
    """Edit one Short, write a new MP4, and update the in-memory result."""

    shorts = result.get("shorts")
    if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
        raise ShortEditError(f"Short index {index} is out of range.")
    entry = shorts[index]
    if not isinstance(entry, dict):
        raise ShortEditError(f"Short index {index} is invalid.")

    output = output.expanduser().resolve()
    shorts_path = output / "shorts.json"
    state_path = output / "project_state.json"
    try:
        state = ProjectState.model_validate_json(state_path.read_text(encoding="utf-8"))
        report = json.loads(shorts_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateNotReadyError(
            f"Cannot read the completed Shorts project: {exc}"
        ) from exc
    if state.media_info is None:
        raise StateNotReadyError("The project has no media metadata.")

    raw_pieces = entry.get("pieces")
    if not isinstance(raw_pieces, list) or not raw_pieces:
        raise ShortEditError("The Short has no source pieces.")
    try:
        pieces = [(int(piece[0]), int(piece[1])) for piece in raw_pieces]
    except (TypeError, ValueError, IndexError) as exc:
        raise ShortEditError("The Short pieces are invalid.") from exc

    rate = state.media_info.audio_sample_rate
    total = sum(end - start for start, end in pieces)
    start_sample = round((options.start_sec or 0.0) * rate)
    end_sample = round(
        (options.end_sec if options.end_sec is not None else total / rate) * rate
    )
    end_sample = min(end_sample, total)
    trimmed = slice_pieces(pieces, start_sample, end_sample)
    if not trimmed:
        raise ShortEditError("The trim leaves no video.")

    title = options.title or str(entry.get("title") or "Short")
    aspect = options.aspect_ratio or str(
        entry.get("aspect_ratio") or state.modules_config.shorts.aspect_ratio
    )
    width, height = short_dimensions(aspect)
    base_style = state.modules_config.shorts.caption_style
    if isinstance(entry.get("caption_style"), dict):
        with contextlib.suppress(ValidationError):
            base_style = CaptionStyle.model_validate(
                {**base_style.model_dump(), **entry["caption_style"]}
            )
    style = base_style
    if options.caption_style:
        try:
            style = CaptionStyle.model_validate(
                {**base_style.model_dump(), **options.caption_style}
            )
        except ValidationError as exc:
            raise ShortEditError(f"Invalid caption style: {exc}") from exc

    burn_subtitles = (
        options.burn_subtitles
        if options.burn_subtitles is not None
        else bool(entry.get("subtitles"))
    )
    kept = [item for item in state.transcript if item.id not in set(state.retake_culls)]
    edited_dir = output / "shorts" / "edited"
    edited_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    slug = slugify(title, index + 1)
    ass_path: Path | None = None
    if burn_subtitles:
        lines = caption_lines(
            kept,
            trimmed,
            sample_rate=rate,
            word_timing=style.word_timing,
        )
        if lines:
            ass_path = edited_dir / f"{slug}-{stamp}.ass"
            ass_path.write_text(
                build_ass_lines(lines, style=style, width=width, height=height),
                encoding="utf-8",
            )
        else:
            events = sentence_events(kept, trimmed, sample_rate=rate)
            if events:
                ass_path = edited_dir / f"{slug}-{stamp}.ass"
                ass_path.write_text(
                    build_ass(events, style=style, width=width, height=height),
                    encoding="utf-8",
                )

    destination = edited_dir / f"{slug}-{stamp}.mp4"
    FFmpegAdapter().render_short(
        source,
        trimmed,
        destination,
        sample_rate=rate,
        ass_path=ass_path,
        width=width,
        height=height,
    )

    previous_path = entry.get("path")
    duration_sec = sum(end - start for start, end in trimmed) / rate
    entry.update(
        {
            "title": title,
            "pieces": [[start, end] for start, end in trimmed],
            "start_sample": trimmed[0][0],
            "end_sample": trimmed[-1][1],
            "start_sec": round(trimmed[0][0] / rate, 3),
            "end_sec": round(trimmed[-1][1] / rate, 3),
            "duration_sec": round(duration_sec, 3),
            "aspect_ratio": aspect,
            "width": width,
            "height": height,
            "path": str(destination),
            "caption_style": style.model_dump(mode="json"),
            "edited_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "edit_count": int(entry.get("edit_count", 0)) + 1,
        }
    )
    if ass_path is not None:
        entry["subtitles"] = str(ass_path)
    else:
        entry.pop("subtitles", None)
    if previous_path is not None:
        entry["previous_path"] = previous_path
    entry["sentence_ids"] = [
        sentence.id
        for sentence in kept
        if any(
            sentence.end_sample > start and sentence.start_sample < end
            for start, end in trimmed
        )
    ]
    clips = report.get("clips")
    if isinstance(clips, list) and 0 <= index < len(clips):
        clips[index] = entry
    output_clips = clips if isinstance(clips, list) else shorts
    shorts_path.write_text(
        json.dumps({"ok": True, "clips": output_clips}, indent=2) + "\n",
        encoding="utf-8",
    )
    shorts[index] = entry
    return entry
