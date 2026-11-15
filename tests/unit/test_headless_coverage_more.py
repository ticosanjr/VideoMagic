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

    monkeypatch.setattr(assets_screen_capture, "_browser", lambda: "/bin/true")
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

    monkeypatch.setattr(video_export, "export_mp4", fake_export)
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
    monkeypatch.setattr(qa_visual, "analyze_frames", lambda *args: [])
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
    monkeypatch.setattr(assets_screen_capture, "find_binary", lambda name: None)
    assert assets_screen_capture._browser() is None


def test_render_gate_reset(tmp_path: Path) -> None:
    from videoflow.application.render_gate import reset_gate

    gate = reset_gate(tmp_path / "x.lock")
    assert gate.status()["queued"] == 0


def test_tool_beatmap_execute_starts_a_job(tmp_path: Path, monkeypatch) -> None:
    from videoflow.mcp_server.tools_headless import register_headless_tools

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    tools: dict[str, object] = {}

    class Job:
        job_id = "job-1"

        def to_dict(self):
            return {"job_id": self.job_id}

    class Manager:
        @staticmethod
        def start(*args, **kwargs):
            return Job()

    class FakeContext:
        last: dict[str, object] = {}
        manager = Manager()

        @staticmethod
        def timeline_job(job_id=None):
            return SimpleNamespace(source=source, output=tmp_path / "out", result={})

    def register(func):
        tools[func.__name__] = func
        return func

    register_headless_tools(register, FakeContext())
    manifest = {
        "project_id": "p",
        "metadata": {"source": str(source), "recipe": "opencode_clone_style"},
        "scenes": [],
    }
    result = tools["vf_beatmap_execute"](manifest=manifest)
    assert result["ok"] is True


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


def test_audio_patch_apply_branch(tmp_path: Path, monkeypatch) -> None:
    from videoflow.mcp_server import tools_headless

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    context = _context(tmp_path)
    context.transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=24000,
            text="old",
            words=[],
        )
    ]
    context.state.transcript = context.transcript
    (context.output / "audio").mkdir(parents=True, exist_ok=True)
    (context.output / "audio" / "master.wav").write_bytes(b"master")
    job = SimpleNamespace(source=context.source, output=context.output, result={})
    tools: dict[str, object] = {}

    class FakeContext:
        last: dict[str, object] = {}
        manager = SimpleNamespace()

        @staticmethod
        def timeline_job(job_id=None):
            return job

        @staticmethod
        def state_for_job(_job):
            return context.state

    def register(func):
        tools[func.__name__] = func
        return func

    class FakeTts:
        def __init__(self, **kwargs):
            pass

        def synthesize(self, text, destination):
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            Path(destination).write_bytes(b"tts")
            return Path(destination)

    monkeypatch.setenv("VIDEOWFLOW_TTS_BASE_URL", "http://tts.local/v1")
    monkeypatch.setattr("videoflow.adapters.tts.OpenAITtsAdapter", FakeTts)
    monkeypatch.setattr(
        tools_headless,
        "patch_audio",
        lambda *args, **kwargs: {"path": str(tmp_path / "patched.wav")},
    )
    tools_headless.register_headless_tools(register, FakeContext())
    result = tools["vf_audio_patch_line"](sentence_id=0, text="new line", apply=True)
    assert result["ok"] is True, result
    assert result["patch"]["patched"]["path"].endswith("patched.wav")


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
