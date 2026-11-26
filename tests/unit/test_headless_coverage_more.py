"""Additional edge coverage for the headless edition."""

from __future__ import annotations

import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import sync
from videoflow.application.render_gate import RenderGate
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import RecipeError
from videoflow.domain.state import MediaInfo, ProjectState, Sentence, WordTiming
from videoflow.steps import (
    assets_screen_capture,
    assets_transformative,
    intro_assemble,
    nle_sync,
    pacing,
    qa_safezone,
    qa_visual,
    sfx_procedural,
    style_reverse,
    video_export,
    vision_gaze,
)
from videoflow.steps.base import StepIO


def _context(tmp: Path, *, with_state: bool = True) -> PipelineContext:
    output = tmp / "out"
    work = output / "work"
    work.mkdir(parents=True, exist_ok=True)
    source = tmp / "source.mp4"
    source.write_bytes(b"x")
    return PipelineContext(
        source=source,
        output=output,
        work=work,
        exports=output / "exports",
        media=MediaInfo(
            source_path=str(source),
            duration_frames=300,
            fps_num=30,
            fps_den=1,
            width=1920,
            height=1080,
            audio_sample_rate=48000,
        )
        if with_state
        else None,
        state=ProjectState() if with_state else None,
    )


def test_safezone_captions_and_passing_box(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.short_captions = {"short": "caption"}
    qa_safezone.SafeZoneStep().run(
        context, qa_safezone.SafeZoneParams(platforms=["reels"]), StepIO()
    )
    assert context.metadata["safezone_report"]["collisions"]
    context.short_captions = {}
    context.metadata.pop("safezone_report", None)
    qa_safezone.SafeZoneStep().run(
        context,
        qa_safezone.SafeZoneParams(platforms=["reels"], caption_box=[0.1, 0.1, 0.2, 0.1]),
        StepIO(),
    )
    assert context.metadata["safezone_report"]["passed"] is True


def test_pacing_without_media_and_with_overlay(tmp_path: Path) -> None:
    context = _context(tmp_path, with_state=False)
    pacing.PacingAuditStep().run(context, pacing.PacingParams(), StepIO())
    assert context.metadata["pacing_plan"] == []


def test_gaze_spans_helper() -> None:
    spans = vision_gaze.GazeStep._spans(
        [(0.0, "camera"), (2.0, "teleprompter"), (4.0, "unknown")], 1.0
    )
    assert spans


def test_sync_invalid_inputs(tmp_path: Path) -> None:
    assert sync.detect_drift_ms(tmp_path / "missing.wav", tmp_path / "missing.wav") is None

    def write(path: Path, rate: int) -> None:
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(b"\0\0" * rate)

    first = tmp_path / "a.wav"
    second = tmp_path / "b.wav"
    write(first, 8000)
    write(second, 16000)
    assert sync.detect_drift_ms(first, second) is None


def test_render_gate_default_status(tmp_path: Path) -> None:
    gate = RenderGate(path=tmp_path / "lock")
    assert gate.status()["cross_process"] is not None
    with gate.hold("test"):
        assert gate.status()["active"] is True


def test_sfx_kinds(tmp_path: Path) -> None:
    context = _context(tmp_path)
    sfx_procedural.ProceduralSfxStep().run(
        context,
        sfx_procedural.ProceduralSfxParams(
            cues=[
                {"kind": "whoosh"},
                {"kind": "click"},
                {"kind": "foley"},
            ]
        ),
        StepIO(),
    )
    assert len(context.metadata["sfx_cues"]) == 3


def test_style_missing_and_transform_failures(tmp_path: Path) -> None:
    context = _context(tmp_path)
    style_reverse.StyleReverseStep().run(
        context, style_reverse.StyleReverseParams(images=[str(tmp_path / "missing.png")]), StepIO()
    )
    assert context.metadata["style_preset"]["palette"] == []
    assets_transformative.TransformativeGuardStep().run(
        context,
        assets_transformative.TransformativeParams(sources=[str(tmp_path / "missing.mp4")]),
        StepIO(),
    )
    assert context.metadata["transformative_records"] == []


def test_intro_artifacts_and_screen_failure(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    context.artifacts["motion_assets"] = str(tmp_path / "motion.mp4")
    intro_assemble.IntroAssembleStep().run(context, intro_assemble.IntroAssembleParams(), StepIO())
    assert context.metadata["intro_plan"]["segments"]

    class Completed:
        returncode = 1
        stderr = "fail"

    monkeypatch.setattr(assets_screen_capture, "find_browser", lambda: "/bin/true")
    monkeypatch.setattr(assets_screen_capture.subprocess, "run", lambda *a, **k: Completed())
    assets_screen_capture.ScreenCaptureStep().run(
        context,
        assets_screen_capture.ScreenCaptureParams(urls=["https://example.com"]),
        StepIO(),
    )
    assert context.metadata["captured_assets"] == []


def test_qa_visual_error_and_repeated_word(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(qa_visual, "find_binary", lambda name: None)
    assert qa_visual.extract_window(context.source, tmp_path / "f", 0, 1, 10) == []
    assert qa_visual.analyze_frames([tmp_path / "missing.jpg"]) == []

    class Completed:
        returncode = 1
        stderr = "fail"

    monkeypatch.setattr(qa_visual, "find_binary", lambda name: "/bin/ffmpeg")
    monkeypatch.setattr(qa_visual.subprocess, "run", lambda *a, **k: Completed())
    assert qa_visual.extract_window(context.source, tmp_path / "f", 0, 1, 10) == []


def test_nle_corrupt_and_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    context = _context(tmp_path)
    corrupt = context.output / "bad.fcpxml"
    corrupt.write_text("<not xml", encoding="utf-8")
    nle_sync.NleSyncStep().run(
        context, nle_sync.NleSyncParams(format="fcpxml", path=str(corrupt)), StepIO()
    )
    assert context.metadata["sync_back_report"]["warnings"]


def test_video_export_draft_scale(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    context.state.video_segments = []
    captured: dict[str, object] = {}

    def fake_export(state, destination, **kwargs):
        captured.update(kwargs)
        Path(destination).write_bytes(b"mp4")

    monkeypatch.setattr(video_export, "render_master", fake_export)
    video_export.VideoExportStep().run(
        context, video_export.VideoExportParams(draft_scale=0.5), StepIO()
    )
    assert captured["scale_height"] == 540


def test_qa_visual_repeated_word_and_fail(tmp_path: Path, monkeypatch) -> None:
    from videoflow.domain.state import Sentence, VideoSegment, WordTiming

    context = _context(tmp_path)
    context.state.video_segments = [
        VideoSegment(
            clip_id="c",
            source_in_frame=0,
            source_out_frame=300,
            timeline_in_frame=0,
            timeline_out_frame=300,
        )
    ]
    context.transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=4800,
            text="go go",
            words=[
                WordTiming(word="go", start_sample=0, end_sample=2000, probability=0.9),
                WordTiming(word="go", start_sample=2000, end_sample=4000, probability=0.9),
            ],
        )
    ]
    monkeypatch.setattr(qa_visual, "extract_window", lambda *args: [tmp_path / "f.jpg"])
    monkeypatch.setattr(qa_visual, "analyze_frames", lambda *args, **kwargs: [])
    with pytest.raises(RecipeError):
        qa_visual.VisualQaStep().run(
            context, qa_visual.VisualQaParams(fail_on_defects=True), StepIO()
        )


def test_pacing_overlay_skip(tmp_path: Path) -> None:
    from videoflow.domain.state import OverlayClip, VideoSegment

    context = _context(tmp_path)
    context.state.video_segments = [
        VideoSegment(
            clip_id="c",
            source_in_frame=0,
            source_out_frame=300,
            timeline_in_frame=0,
            timeline_out_frame=300,
        )
    ]
    context.state.overlays = [
        OverlayClip(
            overlay_id="o",
            path="/tmp/o.png",
            start_frame=0,
            duration_frames=300,
        )
    ]
    pacing.PacingAuditStep().run(context, pacing.PacingParams(), StepIO())
    assert context.metadata["pacing_plan"] == []


def test_nle_helpers_and_corrupt(tmp_path: Path, monkeypatch) -> None:
    assert nle_sync._seconds("0s") == 0.0
    assert nle_sync._seconds("bad") == 0.0
    path = tmp_path / "x.fcpxml"
    path.write_text(
        "<fcpxml><clip duration='1s'/><asset-clip duration='2s' offset='1s'/></fcpxml>",
        encoding="utf-8",
    )
    assert nle_sync._clip_count(path, "fcpxml") == 2


def test_screen_capture_browser_lookup(monkeypatch) -> None:
    from videoflow.domains.vision import browser

    monkeypatch.setattr(browser.commands, "resolve_binary", lambda *a, **k: None)
    monkeypatch.setattr(browser, "_windows_candidates", lambda: [])
    assert assets_screen_capture.find_browser() is None


def test_render_gate_reset(tmp_path: Path) -> None:
    from videoflow.application.render_gate import reset_gate

    gate = reset_gate(tmp_path / "x.lock")
    assert gate.status()["queued"] == 0



def test_transcribe_fixed_offset(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps import transcribe as transcribe_module

    class FakeHttp:
        def __init__(self, **kwargs):
            pass

        def transcribe(self, wav, sample_rate):
            return [
                Sentence(
                    id=0,
                    start_sample=200,
                    end_sample=800,
                    text="hello",
                    words=[
                        WordTiming(
                            word="hello",
                            start_sample=200,
                            end_sample=800,
                            probability=0.9,
                        )
                    ],
                )
            ]

    class Pcm:
        def extract_pcm(self, source, destination, **kwargs):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"RIFF")
            return destination

    monkeypatch.setattr(transcribe_module, "WhisperHttpAdapter", FakeHttp)
    context = _context(tmp_path)
    context.speech_intervals = [(0, 48000)]
    context.pcm_digest = "digest"
    transcribe_module.TranscribeStep().run(
        context,
        transcribe_module.TranscribeParams(
            mode="http",
            base_url="http://asr.local/v1",
            offset_mode="fixed",
            offset_ms=100,
        ),
        StepIO(adapter=Pcm()),
    )
    assert context.metadata["sync_report"]["applied"] is True



def test_web_render_html_branch(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import web_render

    scene = tmp_path / "scene"
    scene.mkdir()
    (scene / "index.html").write_text("<h1>x</h1>", encoding="utf-8")

    def fake_shot(browser, url, target, width, height, **kwargs):
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(b"png")
        return True

    def fake_run(command, **kwargs):
        target = Path(command[-1])
        target.write_bytes(b"video")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(web_render, "browser_binary", lambda: "/bin/true")
    monkeypatch.setattr(web_render, "_screenshot", fake_shot)
    monkeypatch.setattr(web_render, "find_binary", lambda name: "/bin/ffmpeg")
    monkeypatch.setattr(web_render.subprocess, "run", fake_run)
    target = web_render.render_html_scene(
        scene,
        "index.html",
        tmp_path / "motion.mp4",
        duration_sec=0.2,
        fps=5,
        width=320,
        height=240,
    )
    assert target.is_file()


def test_nle_sync_apply_updates_timeline(tmp_path: Path, monkeypatch) -> None:
    from videoflow.domain.state import VideoSegment

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    context = _context(tmp_path)
    context.state.video_segments = [
        VideoSegment(
            clip_id="a",
            source_in_frame=0,
            source_out_frame=100,
            timeline_in_frame=0,
            timeline_out_frame=100,
        ),
        VideoSegment(
            clip_id="b",
            source_in_frame=100,
            source_out_frame=200,
            timeline_in_frame=100,
            timeline_out_frame=200,
        ),
    ]
    path = context.output / "edit.fcpxml"
    path.write_text(
        "<fcpxml><clip duration='1s' offset='0s'/><asset-clip duration='2s' offset='1s'/></fcpxml>",
        encoding="utf-8",
    )
    nle_sync.NleSyncStep().run(
        context,
        nle_sync.NleSyncParams(format="fcpxml", path=str(path), apply=True),
        StepIO(),
    )
    report = context.metadata["sync_back_report"]
    assert report["applied"] is True
    assert report["changed_clips"] == 2
    assert context.state.video_segments[1].timeline_in_frame == 30


def test_qa_visual_helpers(tmp_path: Path, monkeypatch) -> None:
    import sys
    import wave
    from types import SimpleNamespace

    from videoflow.domain.state import OverlayClip
    from videoflow.steps import qa_visual

    pcm = tmp_path / "pcm.wav"
    with wave.open(str(pcm), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes((10000).to_bytes(2, "little", signed=True) * 8000)
    assert qa_visual._audio_energy(pcm, 0.0, 0.1, 8000) > 0

    from PIL import Image

    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    Image.new("RGB", (8, 8), (0, 0, 0)).save(first)
    Image.new("RGB", (8, 8), (255, 255, 255)).save(second)
    assert qa_visual._motion_score([first, second]) > 0

    context = _context(tmp_path)
    context.state.overlays = [
        OverlayClip(
            overlay_id="o",
            path="/tmp/o.png",
            start_frame=0,
            duration_frames=10,
            anchor="center",
            margin_x=0,
            margin_y=0,
            z=20,
            width_ratio=0.4,
        )
    ]
    assert qa_visual._overlay_boxes(context)

    fake_cv2 = SimpleNamespace(
        data=SimpleNamespace(haarcascades="x"),
        COLOR_BGR2GRAY=1,
        CascadeClassifier=lambda path: SimpleNamespace(
            detectMultiScale=lambda gray, a, b: [(30, 30, 40, 40)]
        ),
        imread=lambda path: object(),
        cvtColor=lambda image, code: SimpleNamespace(shape=(100, 100)),
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    assert qa_visual._face_obstruction(context, [first], 0.0, 10)

    fake_ocr = SimpleNamespace(image_to_string=lambda path: "wrong text")
    monkeypatch.setitem(sys.modules, "pytesseract", fake_ocr)
    context.metadata["text_expectations"] = [{"start_sec": 0.0, "text": "expected"}]
    assert qa_visual._text_late(context, [first], 0.0, 1.0, 10)

    context.pcm_path = pcm
    monkeypatch.setattr(qa_visual, "extract_window", lambda *args: [first])
    monkeypatch.setattr(qa_visual, "analyze_frames", lambda *args, **kwargs: [])
    qa_visual.VisualQaStep().run(context, qa_visual.VisualQaParams(checks=["lip_sync"]), StepIO())
    assert context.metadata["qa_report"]["checked_windows"] >= 1
