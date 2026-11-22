from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from videoflow.application.short_composition.captions import (
    CaptionBlock,
    CaptionWord,
    assign_layouts,
    build_short_ass,
    group_words,
    sanitize_blocks,
    wrap_words,
)
from videoflow.application.short_composition.plan import resolve_draft
from videoflow.application.short_composition.planner import deterministic_draft
from videoflow.application.short_composition.rhythm import (
    end_settings,
    layout_sfx_cues,
    snap_boundaries,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.domain.state import Sentence, WordTiming
from videoflow.steps.base import StepIO
from videoflow.steps.short_captions import ShortCaptionsParams, ShortCaptionsStep


def _manifest() -> ScenesManifest:
    def scene(scene_id: str, start: float, end: float, layout: str, hints: list[str]):
        return SceneEntry(
            scene_id=scene_id,
            start_sample=round(start * 48_000),
            end_sample=round(end * 48_000),
            start_sec=start,
            end_sec=end,
            layout_type=layout,  # type: ignore[arg-type]
            face_count=1,
            face_bbox_norm={"cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3},
            face_area_ratio=0.06,
            edge_density=0.2 if layout.startswith("SCREEN") else 0.02,
            sharpness_laplacian=120.0,
            editing_hints=hints,
        )

    return ScenesManifest(
        video_id="sha",
        resolution={"w": 1920, "h": 1080},
        fps_num=30,
        fps_den=1,
        scenes=[
            scene("SC_0001", 0.0, 8.0, "TALKING_HEAD", ["SAFE_FOR_BROLL"]),
            scene("SC_0002", 8.0, 20.0, "SCREEN_SHARE_PIP", ["PROTECT_FROM_BROLL"]),
            scene("SC_0003", 20.0, 30.0, "TALKING_HEAD", ["SAFE_FOR_BROLL"]),
        ],
    )


def _plan():
    manifest = _manifest()
    draft = deterministic_draft(manifest, short_id="SH", start_sec=0, end_sec=30)
    return resolve_draft(draft, manifest).plan, manifest


def _transcript(offset: float = 0.1) -> list[Sentence]:
    words = []
    for index in range(60):
        start = round((offset + index * 0.5) * 48_000)
        words.append(
            WordTiming(
                word=f"w{index}",
                start_sample=start,
                end_sample=start + 20_000,
                probability=0.95,
            )
        )
    return [
        Sentence(
            id=0,
            start_sample=words[0].start_sample,
            end_sample=words[-1].end_sample,
            text=" ".join(word.word for word in words),
            words=words,
        )
    ]


def test_wrap_and_group_words_respect_limits() -> None:
    tokens = ["alpha", "bravo", "charlie", "delta", "echo"]
    lines = wrap_words(tokens, max_chars=18, max_lines=2)
    assert lines is not None
    assert len(lines) <= 2
    assert all(len(line) <= 18 for line in lines)
    assert wrap_words(tokens, max_chars=5, max_lines=1) is None

    words = [
        CaptionWord(start=index * 0.4, end=index * 0.4 + 0.35, text=f"word{index}")
        for index in range(9)
    ]
    blocks, warnings = group_words(words, max_words=4, min_words=3)
    assert warnings == []
    assert all(1 <= len(block.text.split()) <= 4 for block in blocks)
    assert sum(len(block.text.split()) for block in blocks) == 9
    assert [len(block.text.split()) for block in blocks] == [3, 3, 3]


def test_group_breaks_on_sentence_end_and_layout_boundary() -> None:
    words = [
        CaptionWord(0.0, 0.3, "hello"),
        CaptionWord(0.4, 0.7, "world."),
        CaptionWord(0.8, 1.1, "next"),
    ]
    blocks, _ = group_words(words)
    assert [block.text for block in blocks] == ["hello world.", "next"]
    crossing = [
        CaptionWord(0.0, 0.3, "a"),
        CaptionWord(0.4, 0.7, "b"),
        CaptionWord(2.0, 2.3, "c"),
        CaptionWord(2.4, 2.7, "d"),
    ]
    blocks, _ = group_words(crossing, layout_boundaries=[1.0], min_words=2)
    assert len(blocks) == 2


def test_sanitizer_removes_overlaps_and_tiny_blocks() -> None:
    blocks = [
        CaptionBlock(0.0, 1.0, ("one",)),
        CaptionBlock(0.5, 2.0, ("two",)),
        CaptionBlock(2.0, 2.01, ("tiny",)),
    ]
    clean, warnings = sanitize_blocks(blocks)
    assert all(
        left.end <= right.start for left, right in zip(clean, clean[1:], strict=False)
    )
    assert any("CAPTION_OVERLAP" in warning for warning in warnings)
    assert all(block.end - block.start >= 0.06 for block in clean)


def test_assign_layouts_trims_and_uses_each_subtitle_y() -> None:
    plan, _manifest_data = _plan()
    blocks = [CaptionBlock(0.0, 9.0, ("alpha",))]
    assigned, warnings = assign_layouts(
        blocks,
        plan,
        subtitle_y={
            "FULL_FACE": 1360,
            "SPLIT_BROLL": 960,
            "SPLIT_SCREEN_SAFE": 840,
            "SPLIT_SCREEN_FILL": 768,
        },
    )
    assert assigned[0].layout == "FULL_FACE"
    assert assigned[0].subtitle_y == 1360
    assert assigned[0].end == plan.segments[0].rel_end
    assert warnings


def test_ass_has_per_block_y_and_line_breaks() -> None:
    blocks = [
        CaptionBlock(0.0, 1.0, ("FIRST",), layout="FULL_FACE", subtitle_y=1360),
        CaptionBlock(1.0, 2.0, ("SECOND", "LINE"), layout="SPLIT_SCREEN_SAFE", subtitle_y=840),
    ]
    text = build_short_ass(blocks)
    assert "PlayResX: 1080" in text
    assert "PlayResY: 1920" in text
    assert "\\an5\\pos(540,1360)" in text
    assert "\\an5\\pos(540,840)" in text
    assert "SECOND\\NLINE" in text
    assert text.count("Dialogue:") == 2


def test_snap_sfx_and_end_settings() -> None:
    plan, _manifest_data = _plan()
    snapped, warnings = snap_boundaries(plan, [8.1, 20.1], tolerance=0.3)
    assert snapped.segments[0].rel_end == 8.1
    assert snapped.segments[1].rel_start == 8.1
    assert snapped.segments[1].rel_end == 20.1
    assert snapped.segments[2].rel_start == 20.1
    assert warnings

    cues = layout_sfx_cues(snapped, asset="whoosh_soft.wav", volume_db=-18)
    assert [cue["time_sec"] for cue in cues] == [8.0, 20.0]
    assert all(cue["volume_db"] == -18 for cue in cues)

    ending = end_settings(snapped)
    assert ending["content_end_sec"] == 30.0
    assert ending["effective_end_sec"] == 30.35
    assert ending["snapped_to"] == "padding"
    assert ending["fade_out_ms"] == 80

    speech = end_settings(snapped, next_speech_sec=30.2)
    assert speech["snapped_to"] == "next_speech"
    assert speech["effective_end_sec"] == 30.18

    valley = end_settings(snapped, rms_valleys=[30.3])
    assert valley["snapped_to"] == "rms_valley"
    assert valley["effective_end_sec"] == 30.3


def _context(tmp_path: Path) -> PipelineContext:
    plan, manifest = _plan()
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
    )
    context.metadata["short_plan"] = plan.model_dump(mode="json")
    context.metadata["scenes_manifest"] = manifest.model_dump(mode="json")
    context.transcript = _transcript()
    return context


def test_short_captions_step_writes_ass_and_cues(tmp_path: Path) -> None:
    context = _context(tmp_path)
    ShortCaptionsStep().run(
        context,
        ShortCaptionsParams(snap_tolerance_sec=0.3, sfx_enabled=True),
        StepIO(),
    )
    cues = json.loads(Path(context.artifacts["short_cues"]).read_text(encoding="utf-8"))
    ass = Path(context.artifacts["short_captions"]).read_text(encoding="utf-8")
    assert cues["caption_count"] > 0
    assert cues["ending"]["snapped_to"] == "padding"
    assert len(cues["sfx"]) == 2
    assert "\\an5\\pos(540,1360)" in ass
    assert "\\an5\\pos(540,840)" in ass
    times = re.findall(r"Dialogue: 0,(\d+:\d+:\d+\.\d+),(\d+:\d+:\d+\.\d+)", ass)
    assert times

    def seconds(value: str) -> float:
        hours, minutes, rest = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(rest)

    ranges = [(seconds(start), seconds(end)) for start, end in times]
    assert all(left[1] <= right[0] for left, right in zip(ranges, ranges[1:], strict=False))
    assert context.metadata["short_plan"]["segments"][0]["rel_end"] == 8.1


def test_short_captions_requires_words(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript = []
    with pytest.raises(StateNotReadyError):
        ShortCaptionsStep().run(context, ShortCaptionsParams(), StepIO())


def test_ass_time_carries_across_minutes() -> None:
    from videoflow.application.short_composition.captions import _ass_time

    assert _ass_time(59.999) == "0:01:00.00"
    assert _ass_time(3599.999) == "1:00:00.00"


def test_short_captions_module_is_a_thin_shim() -> None:
    from pathlib import Path as _Path

    from videoflow.steps import short_captions, shorts_captions

    assert short_captions.ShortCaptionsStep is shorts_captions.ShortCaptionsStep
    assert short_captions.ShortCaptionsParams is shorts_captions.ShortCaptionsParams
    source = _Path(short_captions.__file__).read_text(encoding="utf-8")
    assert len(source.splitlines()) < 20
