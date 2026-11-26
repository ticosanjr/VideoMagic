"""Edge coverage for headless bridges and optional backends."""

from __future__ import annotations

import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application.render_gate import RenderGate
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.steps import (
    assets_screen_capture,
    assets_transformative,
    intro_assemble,
    motion_web_render,
    nle_sync,
    pacing,
    qa_safezone,
    qa_visual,
    style_reverse,
)
from videoflow.steps import (
    ingest as ingest_step,
)
from videoflow.steps.base import StepIO


def _context(tmp: Path, *, state: bool = True) -> PipelineContext:
    output = tmp / "out"
    work = output / "work"
    work.mkdir(parents=True, exist_ok=True)
    source = tmp / "source.mp4"
    source.write_bytes(b"x")
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
        media=media if state else None,
        state=ProjectState() if state else None,
    )


def test_extract_window_command(monkeypatch, tmp_path: Path) -> None:
    def fake_run(command, **kwargs):
        pattern = Path(command[-1])
        pattern.parent.mkdir(parents=True, exist_ok=True)
        for index in range(3):
            (pattern.parent / f"frame-{index:04d}.jpg").write_bytes(b"jpg")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(qa_visual, "find_binary", lambda name: "/bin/ffmpeg")
    monkeypatch.setattr(qa_visual.subprocess, "run", fake_run)
    frames = qa_visual.extract_window(tmp_path / "s.mp4", tmp_path / "f", 1.0, 1.0, 10)
    assert len(frames) == 3
    assert qa_visual.windows_for(_context(tmp_path), 0.5, 3)
    assert qa_visual.windows_for(_context(tmp_path, state=False), 0.5, 3) == []


def test_nle_sync_mlt_and_resolve(monkeypatch, tmp_path: Path) -> None:
    assert nle_sync._seconds("100/30s") == pytest.approx(100 / 30)
    mlt = tmp_path / "out" / "timeline.mlt"
    mlt.parent.mkdir(parents=True, exist_ok=True)
    mlt.write_text("<mlt><playlist><entry in='0' out='10'/></playlist></mlt>", encoding="utf-8")
    context = _context(tmp_path)
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    nle_sync.NleSyncStep().run(
        context, nle_sync.NleSyncParams(format="mlt", path=str(mlt), apply=True), StepIO()
    )
    assert context.metadata["sync_back_report"]["format"] == "mlt"

    nle_sync.NleSyncStep().run(context, nle_sync.NleSyncParams(format="resolve", path=""), StepIO())
    assert context.metadata["sync_back_report"]["warnings"]


def test_transformative_guard_renders(monkeypatch, tmp_path: Path) -> None:
    context = _context(tmp_path)
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")

    def fake_run(command, **kwargs):
        target = Path(command[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"out")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(assets_transformative, "find_binary", lambda name: "/bin/ffmpeg")
    monkeypatch.setattr(assets_transformative.subprocess, "run", fake_run)
    assets_transformative.TransformativeGuardStep().run(
        context,
        assets_transformative.TransformativeParams(sources=[str(source)], apply=True),
        StepIO(),
    )
    assert context.metadata["transformative_records"][0]["note"] == "rendered"


def test_screen_capture_errors(monkeypatch, tmp_path: Path) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(assets_screen_capture, "find_browser", lambda: None)
    with pytest.raises(VideoFlowError):
        assets_screen_capture.ScreenCaptureStep().run(
            context, assets_screen_capture.ScreenCaptureParams(urls=["https://x"]), StepIO()
        )
    monkeypatch.setattr(assets_screen_capture, "find_browser", lambda: "/bin/true")
    assets_screen_capture.ScreenCaptureStep().run(
        context,
        assets_screen_capture.ScreenCaptureParams(
            urls=["https://blocked.test"], allowed_hosts=["allowed.test"]
        ),
        StepIO(),
    )
    assert context.metadata["captured_assets"] == []


def test_pacing_and_safezone_empty_paths(tmp_path: Path) -> None:
    context = _context(tmp_path, state=False)
    pacing.PacingAuditStep().run(context, pacing.PacingParams(), StepIO())
    assert context.metadata["pacing_plan"] == []
    qa_safezone.SafeZoneStep().run(context, qa_safezone.SafeZoneParams(), StepIO())
    assert context.metadata["safezone_report"]["passed"] is True


def test_style_reverse_empty_and_intro_empty(tmp_path: Path) -> None:
    context = _context(tmp_path)
    style_reverse.StyleReverseStep().run(context, style_reverse.StyleReverseParams(), StepIO())
    assert context.metadata["style_preset"]["palette"] == []
    intro_assemble.IntroAssembleStep().run(context, intro_assemble.IntroAssembleParams(), StepIO())
    assert context.metadata["intro_plan"]["segments"] == []


def test_motion_web_render_errors(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(VideoFlowError):
        motion_web_render.WebRenderStep().run(
            context, motion_web_render.WebRenderParams(), StepIO()
        )
    with pytest.raises(VideoFlowError):
        motion_web_render.WebRenderStep().run(
            context,
            motion_web_render.WebRenderParams(command="sh -c 'exit 1'"),
            StepIO(),
        )


def test_render_gate_status_and_lock(tmp_path: Path) -> None:
    gate = RenderGate(path=tmp_path / "render.lock")
    assert gate.status()["active"] is False
    with gate.hold("test", "job"):
        assert gate.status()["active"] is True
    assert gate.status()["active"] is False



def test_ingest_normalises_proxy_and_reference(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    reference = tmp_path / "mic.wav"
    with wave.open(str(reference), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\0\0" * 8000)

    class Adapter:
        def probe(self, path):
            return MediaInfo(
                source_path=str(path),
                duration_frames=300,
                fps_num=30000,
                fps_den=1001,
                width=1920,
                height=1080,
                audio_sample_rate=8000,
            )

        def is_vfr(self, path):
            return True

        def normalize_cfr(self, source, destination, **kwargs):
            Path(destination).write_bytes(b"cfr")
            return Path(destination)

        def build_proxy(self, source, destination, **kwargs):
            Path(destination).write_bytes(b"proxy")
            return Path(destination)

        def extract_pcm(self, source, destination, **kwargs):
            with wave.open(str(destination), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(b"\0\0" * 8000)
            return Path(destination)

        def pcm_digest(self, path):
            return "digest"

    monkeypatch.setattr(ingest_step, "adapter_for", lambda context, io: Adapter())
    context = _context(tmp_path)
    ingest_step.IngestStep().run(
        context,
        ingest_step.IngestParams(
            force_cfr=True,
            generate_proxy=True,
            sync_reference_path=str(reference),
        ),
        StepIO(),
    )
    report = context.metadata["ingest_report"]
    assert report["normalized"]
    assert report["proxy"]
    assert context.pcm_digest == "digest"
