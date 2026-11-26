"""Coverage for the new headless steps, tools, and media helpers."""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path

from videoflow.application import sync
from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, ProjectState, VideoSegment
from videoflow.mcp_server.server import build_server
from videoflow.steps import (
    assets_screen_capture,
    assets_transformative,
    intro_assemble,
    layout_cutout,
    motion_web_render,
    nle_sync,
    qa_visual,
    style_reverse,
    vision_gaze,
)
from videoflow.steps.base import StepIO


def _context(tmp: Path) -> PipelineContext:
    output = tmp / "out"
    work = output / "work"
    work.mkdir(parents=True)
    source = tmp / "source.mp4"
    source.write_bytes(b"fixture")
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
        ),
        state=ProjectState(
            video_segments=[
                VideoSegment(
                    clip_id="c1",
                    source_in_frame=0,
                    source_out_frame=300,
                    timeline_in_frame=0,
                    timeline_out_frame=300,
                )
            ]
        ),
    )


def test_sync_report_modes_and_drift(tmp_path: Path) -> None:
    assert sync.report_for(mode="off", measured_ms=300, threshold_ms=40).applied is False
    assert sync.report_for(mode="auto", measured_ms=10, threshold_ms=40).applied is False
    assert sync.report_for(mode="auto", measured_ms=80, threshold_ms=40).applied is True
    assert sync.report_for(mode="fixed", measured_ms=80, threshold_ms=40).applied is True

    def wav(path: Path, offset: int) -> Path:
        frames = [0] * offset + [10000, -10000] * 2000
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(
                b"".join(int(value).to_bytes(2, "little", signed=True) for value in frames)
            )
        return path

    first = wav(tmp_path / "a.wav", 0)
    second = wav(tmp_path / "b.wav", 160)
    assert sync.detect_drift_ms(first, second) is not None


def test_visual_qa_run_and_windows(tmp_path: Path, monkeypatch) -> None:
    from PIL import Image

    context = _context(tmp_path)
    frames = []
    for index, colour in enumerate([(0, 0, 0), (0, 0, 0), (0, 0, 0), (255, 255, 255)]):
        path = tmp_path / f"f{index}.jpg"
        Image.new("RGB", (16, 16), colour).save(path)
        frames.append(path)
    monkeypatch.setattr(qa_visual, "extract_window", lambda *args: frames)
    qa_visual.VisualQaStep().run(context, qa_visual.VisualQaParams(max_windows=1), StepIO())
    report = context.metadata["qa_report"]
    assert report["checked_windows"] == 1
    assert report["defects"]
    assert qa_visual.windows_for(context, 0.5, 5)


def test_gaze_fallback(tmp_path: Path) -> None:
    context = _context(tmp_path)
    vision_gaze.GazeStep().run(context, vision_gaze.GazeParams(), StepIO())
    spans = context.metadata["gaze_spans"]
    assert spans[0]["state"] == "unknown"
    assert context.warnings


def test_nle_sync_fcpxml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    context = _context(tmp_path)
    path = context.output / "timeline.fcpxml"
    path.write_text(
        "<fcpxml><resources><asset-clip id='x'/></resources></fcpxml>",
        encoding="utf-8",
    )
    nle_sync.NleSyncStep().run(
        context,
        nle_sync.NleSyncParams(format="fcpxml", path=str(path)),
        StepIO(),
    )
    assert context.metadata["sync_back_report"]["format"] == "fcpxml"


def test_transformative_guard_plan(tmp_path: Path) -> None:
    context = _context(tmp_path)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    assets_transformative.TransformativeGuardStep().run(
        context,
        assets_transformative.TransformativeParams(sources=[str(source)], apply=False),
        StepIO(),
    )
    assert context.metadata["transformative_records"][0]["note"] == "plan-only"


def test_screen_capture_writes_screenshot(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)

    class Completed:
        returncode = 0
        stderr = ""

    def fake_run(command, **kwargs):
        screenshot = next(item for item in command if item.startswith("--screenshot="))
        Path(screenshot.split("=", 1)[1]).write_bytes(b"png")
        return Completed()

    monkeypatch.setattr(assets_screen_capture, "find_browser", lambda: "/bin/true")
    monkeypatch.setattr(assets_screen_capture.subprocess, "run", fake_run)
    assets_screen_capture.ScreenCaptureStep().run(
        context,
        assets_screen_capture.ScreenCaptureParams(
            urls=["https://example.com"], allowed_hosts=["example.com"]
        ),
        StepIO(),
    )
    assert context.metadata["captured_assets"][0]["url"] == "https://example.com"


def test_style_reverse_from_image(tmp_path: Path) -> None:
    from PIL import Image

    image = tmp_path / "ref.png"
    Image.new("RGB", (32, 32), (200, 20, 20)).save(image)
    context = _context(tmp_path)
    style_reverse.StyleReverseStep().run(
        context,
        style_reverse.StyleReverseParams(images=[str(image)], palette_count=3),
        StepIO(),
    )
    assert context.metadata["style_preset"]["palette"]


def test_intro_and_layout_plans(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.shorts = [{"title": "Hook", "path": str(tmp_path / "hook.mp4"), "duration_sec": 20}]
    intro_assemble.IntroAssembleStep().run(context, intro_assemble.IntroAssembleParams(), StepIO())
    assert context.metadata["intro_plan"]["segments"]
    layout_cutout.CutoutLayoutStep().run(
        context, layout_cutout.CutoutParams(style="auto"), StepIO()
    )
    assert context.metadata["layout_plan"]["clips"]


def test_motion_web_render_command_bridge(tmp_path: Path) -> None:
    context = _context(tmp_path)
    motion_web_render.WebRenderStep().run(
        context,
        motion_web_render.WebRenderParams(
            command="sh -c 'printf scene > {output}'",
            output_format="mp4",
            draft_scale=0.5,
        ),
        StepIO(),
    )
    assert context.metadata["motion_assets"][0]["draft"] is True


def _call(name: str, arguments: dict[str, object]) -> dict[str, object]:
    async def invoke() -> dict[str, object]:
        result = await build_server().call_tool(name, arguments)
        return dict(result.structured_content or {})  # type: ignore[attr-defined]

    return asyncio.run(invoke())



