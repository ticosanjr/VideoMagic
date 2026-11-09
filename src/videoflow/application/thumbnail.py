"""Generate a PNG thumbnail for one completed Short."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.fonts import fonts_dir
from videoflow.application.shorts import CaptionLine, build_ass_lines
from videoflow.application.shorts_project import (
    load_short_project,
    save_short_entry,
    short_entry,
)
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import ShortEditError


def generate_short_thumbnail(
    *,
    output: Path,
    index: int,
    result: dict[str, Any],
    time_sec: float | None = None,
    title: str | None = None,
    caption_style: dict[str, Any] | None = None,
) -> dict[str, object]:
    entry = short_entry(result, index)
    output = output.expanduser().resolve()
    state, report = load_short_project(output)
    raw_source = entry.get("path")
    if not isinstance(raw_source, str) or not Path(raw_source).is_file():
        raise ShortEditError("The Short MP4 is missing.")
    duration = float(entry.get("duration_sec") or 0.0)
    selected_time = (
        float(time_sec)
        if time_sec is not None
        else min(max(duration * 0.15, 0.2), 2.0)
    )
    if selected_time < 0 or (duration > 0 and selected_time >= duration):
        raise ShortEditError("Thumbnail time is outside the Short.")
    title_text = (title or str(entry.get("title") or "Short")).strip()
    if not title_text:
        raise ShortEditError("Thumbnail title is empty.")
    style = state.modules_config.shorts.caption_style
    if caption_style:
        try:
            style = CaptionStyle.model_validate(
                {**style.model_dump(), **caption_style}
            )
        except ValidationError as exc:
            raise ShortEditError(f"Invalid thumbnail style: {exc}") from exc
    width = int(entry.get("width") or 1080)
    height = int(entry.get("height") or 1920)
    thumb_dir = output / "shorts" / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    ass_path = thumb_dir / f"thumb-{index + 1}-{stamp}.ass"
    ass_path.write_text(
        build_ass_lines(
            [CaptionLine(start=0.0, end=1.0, text=title_text)],
            style=style,
            width=width,
            height=height,
        ),
        encoding="utf-8",
    )
    destination = thumb_dir / f"thumb-{index + 1}-{stamp}.png"
    FFmpegAdapter().render_thumbnail(
        Path(raw_source),
        destination,
        time_sec=selected_time,
        ass_path=ass_path,
        fontsdir=str(fonts_dir()),
    )
    payload = {
        "path": str(destination),
        "title": title_text,
        "time_sec": round(selected_time, 3),
        "width": width,
        "height": height,
    }
    thumbs = entry.get("thumbnails")
    if not isinstance(thumbs, list):
        thumbs = []
    thumbs.append(payload)
    entry["thumbnails"] = thumbs
    entry["thumbnail"] = str(destination)
    save_short_entry(
        output,
        report,
        index,
        entry,
        fallback=result.get("shorts") or [],
    )
    return payload
