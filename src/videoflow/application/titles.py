"""Render the titles plan into an ASS overlay for MP4 previews."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _ass_time(seconds: float) -> str:
    safe = max(0.0, float(seconds))
    hours = int(safe // 3600)
    minutes = int((safe % 3600) // 60)
    whole = int(safe % 60)
    centis = int(round((safe - int(safe)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{whole:02d}.{centis:02d}"


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\N")
    )


def render_titles_ass(
    payload: dict[str, Any],
    target: Path,
    *,
    width: int,
    height: int,
) -> Path:
    """Write title cards and lower thirds as ASS dialogue events."""

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {max(2, width)}",
        f"PlayResY: {max(2, height)}",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        (
            "Style: Title,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,1,4,2,5,60,60,60,1"
        ),
        (
            "Style: LowerThird,Arial,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,"
            "-1,0,0,0,100,100,0,0,3,2,1,1,60,60,80,1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for card in payload.get("title_cards", []):
        if not isinstance(card, dict):
            continue
        if card.get("kind") == "short":
            continue
        text = str(card.get("text") or "").strip()
        if not text:
            continue
        start = float(card.get("start_sec") or 0.0)
        duration = max(0.5, float(card.get("duration_sec") or 2.0))
        lines.append(
            f"Dialogue: 1,{_ass_time(start)},{_ass_time(start + duration)},Title,,0,0,0,,"
            f"{_escape(text)}"
        )
    for item in payload.get("lower_thirds", []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start = float(item.get("start_sec") or 0.0)
        end = max(start + 0.5, float(item.get("end_sec") or start + 3.0))
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},LowerThird,,0,0,0,,"
            f"{_escape(text)}"
        )
    destination = Path(target).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
