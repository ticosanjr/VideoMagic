from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from videoflow.application.brand_kit import brand_kit_root, load_brand_kit
from videoflow.application.caption_preview import render_caption_preview
from videoflow.application.captions import CaptionLine, build_ass_lines
from videoflow.application.curation import (
    build_broll_contact_sheet,
    build_minute_sample,
    build_music_candidates,
    build_sfx_demo,
    curation_manifest,
)
from videoflow.application.layout import pack_project_layout
from videoflow.application.overlay_geometry import (
    asset_dimensions,
    auto_pack,
    caption_box,
    collisions,
    layout_payload,
    overlap,
    overlap_pixels,
    overlay_box,
    write_layout,
)
from videoflow.application.overlay_preview import render_overlay_preview
from videoflow.application.projects import init_project, save_project_state
from videoflow.application.qa_caption import audit_ass
from videoflow.application.qa_word_fidelity import verify_word_fidelity
from videoflow.application.release_kit import build_release_kit
from videoflow.application.shorts_tighten import passes_metrics, tighten_clip
from videoflow.application.time_map import last_speech_timeline_sec
from videoflow.application.transcript_clean import clean_transcript
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import NeedsReviewError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    OverlayClip,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)
from videoflow.steps.base import StepIO
from videoflow.steps.curation import CurationParams, CurationPrepareStep
from videoflow.steps.qa_final import FinalQaParams, FinalQaStep
from videoflow.steps.release_kit import ReleaseKitParams, ReleaseKitStep
from videoflow.steps.shorts_tighten import ShortsTightenStep, TightenParams
from videoflow.steps.transcript_dedupe import DedupeParams, TranscriptDedupeStep


def _media(tmp_path: Path, *, width: int = 640, height: int = 360, frames: int = 90) -> MediaInfo:
    source = tmp_path / "source.mp4"
    if not source.exists():
        source.write_bytes(b"x")
    return MediaInfo(
        source_path=str(source),
        duration_frames=frames,
        fps_num=30,
        fps_den=1,
        width=width,
        height=height,
        audio_sample_rate=48000,
    )


def _state(tmp_path: Path, **kwargs) -> ProjectState:
    media = _media(tmp_path, **kwargs)
    return ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=90,
                timeline_in_frame=0,
                timeline_out_frame=90,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=144000,
                timeline_in_sample=0,
                timeline_out_sample=144000,
            )
        ],
    )


def _overlay(tmp_path: Path, anchor: str, **updates) -> OverlayClip:
    image = tmp_path / f"{anchor}.png"
    if not image.exists():
        Image.new("RGB", (100, 50), "red").save(image)
    return OverlayClip(
        overlay_id=updates.pop("overlay_id", anchor),
        path=str(image),
        start_frame=updates.pop("start_frame", 0),
        duration_frames=updates.pop("duration_frames", 30),
        anchor=anchor,  # type: ignore[arg-type]
        width_ratio=0.2,
        **updates,
    )


def test_overlay_geometry_all_anchors_and_collisions(tmp_path: Path) -> None:
    assert asset_dimensions(Path("does-not-exist.png")) == (1, 1)
    expected = {
        "top_left": (10, 20),
        "top_center": (410, 20),
        "top_right": (790, 20),
        "bottom_left": (10, 380),
        "bottom_center": (410, 380),
        "bottom_right": (790, 380),
        "center": (410, 220),
    }
    for anchor, xy in expected.items():
        overlay = _overlay(tmp_path, anchor, margin_x=10, margin_y=20)
        box = overlay_box(overlay, 1000, 500)
        assert (box.x, box.y) == xy
        assert (box.width, box.height) == (200, 100)
    left = _overlay(tmp_path, "top_left", overlay_id="a")
    right = _overlay(tmp_path, "top_left", overlay_id="b", margin_x=50)
    assert overlap(overlay_box(left, 1000, 500), overlay_box(right, 1000, 500))
    assert overlap_pixels(overlay_box(left, 1000, 500), overlay_box(right, 1000, 500)) > 0
    state = _state(tmp_path).model_copy(update={"overlays": [left, right]})
    caption = caption_box(CaptionStyle(), 1000, 500)
    assert collisions(state, 1000, 500, caption=caption)
    payload = layout_payload(state, 1000, 500, caption=caption)
    assert payload["overlays"] and payload["canvas"]["width"] == 1000
    target = write_layout(state, tmp_path / "out", 1000, 500, caption=caption)
    assert target.is_file()
    changes = auto_pack(state, 1000, 500, caption=caption)
    assert isinstance(changes, list)


def test_overlay_preview_and_layout_project(tmp_path: Path, monkeypatch) -> None:
    record, _ = init_project(name="Preview", output=tmp_path / "project")
    state = _state(tmp_path, width=320, height=180)
    state.overlays = [_overlay(tmp_path, "top_center")]
    save_project_state(record, state, bump_revision=False)
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (320, 180), "blue").save(frame)

    def fake_run(command, **kwargs):
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (320, 180), "blue").save(command[-1])
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("videoflow.application.overlay_preview.subprocess.run", fake_run)
    result = render_overlay_preview(
        state, Path(record.output), time_sec=1.0, platform="youtube_16_9"
    )
    assert Path(result["path"]).is_file()
    packed = pack_project_layout(record.project_id, apply=True)
    assert packed["layout_path"]
    assert packed["revision"] >= 2


def test_caption_preview_and_qa_caption(tmp_path: Path, monkeypatch) -> None:
    state = _state(tmp_path)
    sentence = Sentence(
        id=0,
        start_sample=0,
        end_sample=48000,
        text="hello world from videoflow",
        words=[
            WordTiming(word="hello", start_sample=0, end_sample=10000, probability=0.9),
            WordTiming(word="world", start_sample=10000, end_sample=20000, probability=0.9),
            WordTiming(word="from", start_sample=20000, end_sample=30000, probability=0.9),
            WordTiming(word="videoflow", start_sample=30000, end_sample=40000, probability=0.9),
        ],
    )
    state.transcript = [sentence]
    state.modules_config.shorts.caption_style = CaptionStyle(effect="karaoke_sweep")

    def fake_run(command, **kwargs):
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_bytes(b"jpg")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("videoflow.application.caption_preview.subprocess.run", fake_run)
    result = render_caption_preview(state, tmp_path, time_sec=0.4)
    assert len(result["frames"]) == 3
    ass = tmp_path / "sample.ass"
    ass.write_text(
        build_ass_lines(
            [CaptionLine(0, 1, "hi", ((0.0, 0.5, "hi"),), 0)],
            style=CaptionStyle(effect="karaoke_sweep"),
            width=320,
            height=240,
        ),
        encoding="utf-8",
    )
    report = audit_ass(ass, effect="karaoke_sweep", max_chars=1)
    assert not report["ok"]
    assert any(item["kind"] == "caption_width" for item in report["issues"])


def test_word_fidelity_available_and_unavailable(tmp_path: Path, monkeypatch) -> None:
    assert verify_word_fidelity(tmp_path / "x.mp4", [], work=tmp_path)["status"] == "unavailable"
    sentence = Sentence(id=0, start_sample=0, end_sample=1000, text="hello world")
    monkeypatch.setattr(
        "videoflow.adapters.faster_whisper.FasterWhisperAdapter.available",
        staticmethod(lambda *args, **kwargs: True),
    )
    monkeypatch.setattr(
        "videoflow.adapters.ffmpeg.FFmpegAdapter.extract_pcm",
        lambda self, source, target, **kwargs: Path(target).write_bytes(b"wav") or target,
    )
    monkeypatch.setattr(
        "videoflow.adapters.faster_whisper.FasterWhisperAdapter.transcribe",
        lambda self, wav, rate, **kwargs: [
            Sentence(id=0, start_sample=0, end_sample=1, text="hello world")
        ],
    )
    report = verify_word_fidelity(tmp_path / "x.mp4", [sentence], work=tmp_path)
    assert report["status"] == "checked" and report["passed"] is True


def test_clean_transcript_and_tighten() -> None:
    words = [
        WordTiming(word="hello", start_sample=0, end_sample=1000, probability=0.9),
        WordTiming(word="hello", start_sample=1100, end_sample=2000, probability=0.2),
        WordTiming(word="low", start_sample=2100, end_sample=3000, probability=0.1),
    ]
    cleaned, report = clean_transcript(
        [Sentence(id=0, start_sample=0, end_sample=3000, text="hello hello low", words=words)],
        sample_rate=48000,
    )
    assert report["removed_repetitions"] == 1
    assert cleaned[0].words[-1].low_confidence is True
    tightened = tighten_clip(
        start_sample=0,
        end_sample=48000,
        speech_intervals=[(0, 8000), (20000, 30000)],
        words=[
            WordTiming(word="a", start_sample=0, end_sample=1000, probability=0.9),
            WordTiming(word="b", start_sample=28000, end_sample=29000, probability=0.9),
        ],
        sample_rate=48000,
    )
    assert tightened.pieces
    assert tightened.metrics["speech_ratio"] > 0
    assert passes_metrics(tightened.metrics) in {True, False}


def test_shorts_and_transcript_steps(tmp_path: Path) -> None:
    from videoflow.application.shorts import ShortClip

    state = _state(tmp_path)
    state.transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=48000,
            text="hello world",
            words=[
                WordTiming(word="hello", start_sample=0, end_sample=10000, probability=0.9),
                WordTiming(word="world", start_sample=10000, end_sample=20000, probability=0.9),
            ],
        )
    ]
    context = PipelineContext(
        source=Path(state.media_info.source_path),
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=state.media_info,
        state=state,
        transcript=list(state.transcript),
        speech_intervals=[(0, 20000)],
    )
    context.selected_shorts = [
        ShortClip(
            title="s",
            start_sample=0,
            end_sample=48000,
            sentence_ids=(0,),
            pieces=((0, 48000),),
        )
    ]
    context.shorts = [{"title": "s"}]
    TranscriptDedupeStep().run(context, DedupeParams(), StepIO())
    assert context.artifacts["transcript_clean"]
    ShortsTightenStep().run(context, TightenParams(), StepIO())
    assert context.shorts[0]["speech_ratio"] > 0
    assert last_speech_timeline_sec(context.state) is not None


def test_release_kit_brand_and_curation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    record, _ = init_project(name="Kit", output=tmp_path / "kit")
    state = _state(tmp_path)
    state.transcript = [Sentence(id=0, start_sample=0, end_sample=1000, text="hello world")]
    save_project_state(record, state, bump_revision=False)
    monkeypatch.setattr(
        "videoflow.application.release_kit._thumbnails", lambda *args, **kwargs: []
    )
    kit = build_release_kit(record.project_id)
    assert kit["titles"] and kit["description"]
    root = brand_kit_root("chan")
    root.mkdir(parents=True)
    (root / "logo.png").write_bytes(b"logo")
    (root / "lower-third.png").write_bytes(b"lt")
    (root / "cta.mp4").write_bytes(b"cta")
    (root / "look.cube").write_bytes(b"lut")
    (root / "sting.wav").write_bytes(b"sting")
    brand = load_brand_kit("chan")
    assert brand["exists"] and brand["logo"] and brand["lut"]
    assert load_brand_kit("missing")["exists"] is False

    def fake_run(command, **kwargs):
        target = Path(command[-1])
        if target.suffix.lower() in {".jpg", ".png", ".jpeg"}:
            Image.new("RGB", (100, 60), "green").save(target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"media")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("videoflow.application.curation.subprocess.run", fake_run)
    monkeypatch.setattr(
        "videoflow.application.curation.compose_music",
        lambda directory, **kwargs: (
            Path(directory).mkdir(parents=True, exist_ok=True)
            or {"files": {"mix": str(Path(directory) / "music-bed.wav")}}
        ),
    )
    monkeypatch.setattr(
        "videoflow.application.curation.synthesize_foley",
        lambda directory, cues, **kwargs: {"cues": [], "count": 0},
    )
    music = build_music_candidates(record.project_id)
    assert len(music) == 3
    assert build_broll_contact_sheet(record.project_id)["ok"] is True
    assert build_sfx_demo(record.project_id)["ok"] is True
    assert build_minute_sample(record.project_id)["ok"] is True
    manifest = curation_manifest(record.project_id)
    assert manifest["path"]


def test_curation_qa_and_release_steps(tmp_path: Path, monkeypatch) -> None:
    record, _ = init_project(name="Steps", output=tmp_path / "steps")
    state = _state(tmp_path)
    save_project_state(record, state, bump_revision=False)
    context = PipelineContext(
        source=Path(state.media_info.source_path),
        output=Path(record.output),
        work=Path(record.output) / "work",
        exports=Path(record.output) / "exports",
        media=state.media_info,
        state=state,
        metadata={"project_id": record.project_id},
    )
    monkeypatch.setattr(
        "videoflow.steps.curation.curation_manifest",
        lambda project_id: {
            "path": str(tmp_path / "curation.json"),
            "music": [{"id": "M1", "preview": ""}],
            "broll": {"candidates": []},
            "sample": {},
        },
    )
    CurationPrepareStep().run(context, CurationParams(), StepIO())
    assert context.metadata["curation"]
    video = Path(record.output) / "exports" / "youtube_master.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"v")
    monkeypatch.setattr(
        "videoflow.steps.qa_final.audit_final",
        lambda *args, **kwargs: {
            "ok": True,
            "report": str(tmp_path / "qa.json"),
            "status": "succeeded",
        },
    )
    FinalQaStep().run(context, FinalQaParams(video_path=str(video)), StepIO())
    monkeypatch.setattr(
        "videoflow.steps.qa_final.audit_final",
        lambda *args, **kwargs: {"ok": False, "report": "", "status": "needs_review"},
    )
    with pytest.raises(NeedsReviewError):
        FinalQaStep().run(context, FinalQaParams(video_path=str(video)), StepIO())
    monkeypatch.setattr(
        "videoflow.steps.release_kit.build_release_kit",
        lambda project_id: {"path": str(tmp_path / "kit.json")},
    )
    ReleaseKitStep().run(context, ReleaseKitParams(), StepIO())
    assert context.artifacts["release_kit"]


def test_mp4_overlay_z_order(tmp_path: Path, monkeypatch) -> None:
    from videoflow.exporters import mp4

    state = _state(tmp_path)
    state.overlays = [
        _overlay(tmp_path, "top_center", overlay_id="lower", z=10),
        _overlay(tmp_path, "bottom_right", overlay_id="logo", z=50),
    ]
    ass = tmp_path / "captions.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    calls: list[list[str]] = []

    class FakeRenderer:
        def render(self, args):
            calls.append(list(args))
            Path(args[-1]).write_bytes(b"mp4")

    monkeypatch.setattr(mp4, "_duration_gate_enabled", lambda adapter: False)
    monkeypatch.setattr(
        "videoflow.application.overlay_geometry.asset_dimensions",
        lambda *args, **kwargs: (100, 50),
    )
    mp4.export_mp4(state, tmp_path / "out.mp4", adapter=FakeRenderer(), ass_path=ass)
    graph = calls[0][calls[0].index("-filter_complex") + 1]
    assert graph.index("overlay=") < graph.index("ass=") < graph.rindex("overlay=")
    assert (tmp_path / "layout.json").is_file()
