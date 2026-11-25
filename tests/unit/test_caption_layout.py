from __future__ import annotations

import re
from pathlib import Path

from videoflow.application.captions import CaptionLine, build_ass_lines
from videoflow.application.qa_caption import audit_ass
from videoflow.domain.config import CaptionStyle


def test_vertical_captions_use_short_safe_zone() -> None:
    ass = build_ass_lines(
        [CaptionLine(0, 1, "uma legenda")],
        style=CaptionStyle(),
        width=1080,
        height=1920,
    )
    style_row = next(line for line in ass.splitlines() if line.startswith("Style:"))
    assert style_row.split(",")[-2] == "0"
    assert "\\pos(540,1340)" in ass
    assert "WrapStyle: 0" in ass
    assert style_row.split(",")[-4:-2] == ["140", "140"]


def test_longform_captions_use_lower_margin() -> None:
    ass = build_ass_lines(
        [CaptionLine(0, 1, "a caption")],
        style=CaptionStyle(),
        width=1920,
        height=1080,
    )
    style_row = next(line for line in ass.splitlines() if line.startswith("Style:"))
    assert style_row.split(",")[-2] == "49"
    assert "\\pos(" not in ass


def test_short_safe_zone_overrides_custom_position() -> None:
    ass = build_ass_lines(
        [CaptionLine(0, 1, "custom")],
        style=CaptionStyle(position_x=0.5, position_y=0.8),
        width=1080,
        height=1920,
    )
    assert "\\pos(540,1340)" in ass


def test_overlapping_caption_events_are_trimmed_or_merged() -> None:
    ass = build_ass_lines(
        [
            CaptionLine(0.0, 1.5, "primeira"),
            CaptionLine(0.5, 2.0, "segunda"),
            CaptionLine(2.0, 3.0, "segunda"),
        ],
        width=1080,
        height=1920,
    )
    dialogues = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(dialogues) == 2
    first = dialogues[0].split(",")
    second = dialogues[1].split(",")
    # First ends 15 ms before the second starts.
    assert first[2] == "0:00:00.48"
    assert second[1] == "0:00:00.50"
    # The identical adjacent event is merged into the previous one.
    assert second[2] == "0:00:03.00"


def test_caption_qa_detects_overlap_and_outside_tags(tmp_path: Path) -> None:
    path = tmp_path / "captions.ass"
    path.write_text(
        "[Events]\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,first\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,second\n"
        "Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,literal \\c&H00FF00& text\n",
        encoding="utf-8",
    )
    report = audit_ass(path)
    kinds = {item["kind"] for item in report["issues"]}
    assert "caption_overlap" in kinds
    assert "caption_escape" in kinds


def test_keyword_tags_stay_inside_override_blocks() -> None:
    ass = build_ass_lines(
        [CaptionLine(0, 1, "o resultado final")],
        style=CaptionStyle(
            keyword_highlight_enabled=True,
            keyword_words=["resultado"],
        ),
        width=1080,
        height=1920,
    )
    dialogue = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))
    text = dialogue.split(",", 9)[9]
    outside = re.sub(r"\{[^}]*\}", "", text)
    assert "\\c&H" not in outside
    assert "{\\c&H" in text
