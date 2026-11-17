"""Headless step foundations: safe zones, pacing, SFX, rules, and boards."""

from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, OverlayClip, ProjectState, VideoSegment
from videoflow.steps import (
    assets_reference_board,
    pacing,
    preset_compile,
    qa_safezone,
    qa_visual,
    sfx_procedural,
)
from videoflow.steps.base import StepIO


def _context(tmp: Path, *, state: ProjectState | None = None) -> PipelineContext:
    output = tmp / "out"
    work = output / "work"
    work.mkdir(parents=True)
    source = tmp / "source.mp4"
    source.write_bytes(b"fixture")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=300,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    return PipelineContext(
        source=source,
        output=output,
        work=work,
        exports=output / "exports",
        media=media,
        state=state,
    )


def _state() -> ProjectState:
    return ProjectState(
        video_segments=[
            VideoSegment(
                clip_id="clip-1",
                source_in_frame=0,
                source_out_frame=300,
                timeline_in_frame=0,
                timeline_out_frame=300,
            )
        ],
        overlays=[
            OverlayClip(
                overlay_id="overlay-1",
                path=str(Path("/tmp/overlay.png")),
                start_frame=0,
                duration_frames=30,
                position_x=0.5,
                position_y=0.9,
                width_ratio=0.3,
            )
        ],
    )


def test_safezone_flags_bottom_overlay(tmp_path: Path) -> None:
    context = _context(tmp_path, state=_state())
    qa_safezone.SafeZoneStep().run(
        context, qa_safezone.SafeZoneParams(platforms=["reels"]), StepIO()
    )
    report = context.metadata["safezone_report"]
    assert report["passed"] is False
    assert report["collisions"][0]["platform"] == "reels"


def test_pacing_marks_a_long_static_shot(tmp_path: Path) -> None:
    state = _state()
    state.overlays = []
    context = _context(tmp_path, state=state)
    pacing.PacingAuditStep().run(
        context,
        pacing.PacingParams(short_static_sec=5.0, long_static_sec=12.0),
        StepIO(),
    )
    plan = context.metadata["pacing_plan"]
    assert len(plan) == 1
    assert plan[0]["action"] == "zoom"


def test_procedural_sfx_writes_a_wav(tmp_path: Path) -> None:
    context = _context(tmp_path)
    sfx_procedural.ProceduralSfxStep().run(
        context,
        sfx_procedural.ProceduralSfxParams(
            cues=[{"kind": "riser", "start_sec": 1.0, "duration_sec": 0.2}]
        ),
        StepIO(),
    )
    cue = context.metadata["sfx_cues"][0]
    path = Path(cue["path"])
    assert path.is_file()
    assert path.stat().st_size > 44


def test_preset_rulebook_merges_and_versions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    context = _context(tmp_path)
    step = preset_compile.CompileRuleStep()
    params = preset_compile.CompileRuleParams(
        channel_id="canal-paula",
        review_notes=["Use open loops", "Use open loops", "Avoid long silences"],
    )
    step.run(context, params, StepIO())
    from videoflow.application.preset_rules import load_rulebook

    book = load_rulebook("canal-paula")
    assert book.version == 2
    assert len(book.learned_rules) == 2
    assert book.learned_rules[0].weight == 1.25
    assert book.hard_constraints.model_dump() == {
        "palette": "",
        "cut_rhythm_sec": 0.0,
        "broll_style": "",
        "jargon": True,
        "aspect_ratio": "",
        "caption_preset": "",
        "lut": "",
        "music": "",
    }


def test_reference_board_writes_a_contact_sheet(tmp_path: Path) -> None:
    from PIL import Image

    image = tmp_path / "person.png"
    Image.new("RGB", (64, 64), (20, 120, 220)).save(image)
    context = _context(tmp_path)
    assets_reference_board.ReferenceBoardStep().run(
        context,
        assets_reference_board.ReferenceBoardParams(
            entities=["Paula"], units=["unit-1"], paths=[str(image)]
        ),
        StepIO(),
    )
    board = context.metadata["reference_board"]
    assert Path(board["path"]).is_file()
    assert board["entries"][0]["entity"] == "Paula"


def test_visual_qa_detects_flash_and_duplicate_frames(tmp_path: Path) -> None:
    from PIL import Image

    frames = []
    for index, colour in enumerate([(10, 10, 10), (10, 10, 10), (10, 10, 10), (240, 240, 240)]):
        path = tmp_path / f"frame-{index:04d}.jpg"
        Image.new("RGB", (32, 32), colour).save(path)
        frames.append(path)
    defects = qa_visual.analyze_frames(frames)
    kinds = {kind for kind, _ in defects}
    assert "duplicate_animation" in kinds
    assert "flash" in kinds
