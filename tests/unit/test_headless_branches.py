"""Branch coverage for headless tools, transcribe fallbacks, and sync."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from videoflow.application import render_gate as render_gate_module
from videoflow.application import sync
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.state import MediaInfo
from videoflow.steps import transcribe as transcribe_module
from videoflow.steps.base import StepIO


def _context(tmp: Path) -> PipelineContext:
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
        ),
    )


def test_supports_keyword_and_available_mode_fallback(tmp_path: Path, monkeypatch) -> None:
    assert transcribe_module._supports_keyword(object(), "x") is False
    monkeypatch.setattr(
        "videoflow.application.models.list_models",
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    context = _context(tmp_path)
    assert transcribe_module.TranscribeStep._available_mode(context, StepIO()) in {
        "none",
        "http",
        "faster_whisper",
        "whisper_cpp",
    }


def test_transcribe_rejects_unknown_and_wrong_models(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    with pytest.raises(VideoFlowError):
        transcribe_module.TranscribeStep().run(
            context,
            transcribe_module.TranscribeParams(model_id="missing"),
            StepIO(),
        )
    monkeypatch.setattr(
        "videoflow.application.models.list_models",
        lambda: [{"id": "x", "capability": "llm", "kind": "local", "installed": True}],
    )
    monkeypatch.setattr("videoflow.application.models.installed_path", lambda _id: tmp_path)
    with pytest.raises(VideoFlowError):
        transcribe_module.TranscribeStep().run(
            context,
            transcribe_module.TranscribeParams(model_id="x"),
            StepIO(),
        )
    monkeypatch.setattr(
        "videoflow.application.models.list_models",
        lambda: [{"id": "x", "capability": "asr", "kind": "other", "installed": True}],
    )
    with pytest.raises(VideoFlowError):
        transcribe_module.TranscribeStep().run(
            context,
            transcribe_module.TranscribeParams(model_id="x"),
            StepIO(),
        )


def test_sync_read_wav_rejects_stereo(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\0\0" * 100)
    assert sync.detect_drift_ms(path, path) is None


def test_render_gate_uses_cross_process_lock(tmp_path: Path) -> None:
    gate = render_gate_module.RenderGate(path=tmp_path / "lock")
    with gate.hold("test"):
        assert gate.status()["cross_process"] is True


def test_web_render_helpers(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import web_render

    monkeypatch.setattr(
        web_render, "find_binary", lambda name: "/bin/chrome" if name == "google-chrome" else None
    )
    assert web_render.browser_binary() == "/bin/chrome"

    class Completed:
        returncode = 0

    def fake_run(command, **kwargs):
        target = next(item for item in command if item.startswith("--screenshot="))
        Path(target.split("=", 1)[1]).write_bytes(b"png")
        return Completed()

    monkeypatch.setattr(web_render.subprocess, "run", fake_run)
    target = tmp_path / "shot.png"
    assert web_render._screenshot("/bin/chrome", "https://x", target, 100, 100, alpha=True) is True


def test_audio_patch_errors(tmp_path: Path, monkeypatch) -> None:
    from videoflow.domains.audio import patch as audio_patch

    master = tmp_path / "master.wav"
    patch = tmp_path / "line.wav"
    master.write_bytes(b"x")
    patch.write_bytes(b"y")
    monkeypatch.setattr(audio_patch, "find_binary", lambda name: None)
    with pytest.raises(RuntimeError):
        audio_patch.patch_audio(master, patch, start_sec=0, end_sec=1, output=tmp_path / "o.wav")
    monkeypatch.setattr(audio_patch, "find_binary", lambda name: f"/bin/{name}")

    class Completed:
        returncode = 1
        stderr = "boom"
        stdout = ""

    monkeypatch.setattr(audio_patch.subprocess, "run", lambda *a, **k: Completed())
    with pytest.raises(RuntimeError):
        audio_patch.patch_audio(master, patch, start_sec=0, end_sec=1, output=tmp_path / "o.wav")
    with pytest.raises(FileNotFoundError):
        audio_patch.patch_audio(
            tmp_path / "missing.wav", patch, start_sec=0, end_sec=1, output=tmp_path / "o.wav"
        )



def test_screen_capture_clip_errors(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps import assets_screen_capture

    monkeypatch.setattr(assets_screen_capture, "find_binary", lambda name: None)
    assert (
        assets_screen_capture.ScreenCaptureStep._capture_clip(
            "/bin/true",
            "https://x",
            tmp_path / "x.mp4",
            assets_screen_capture.ScreenCaptureParams(),
        )
        is False
    )


def test_pacing_no_media_and_nle_mlt(tmp_path: Path) -> None:
    from videoflow.steps import nle_sync, pacing

    context = _context(tmp_path)
    context.media = None
    assert pacing.PacingAuditStep._has_overlay(context, 0, 1) is False

    path = tmp_path / "x.mlt"
    path.write_text("<mlt><playlist><entry in='0' out='9'/></playlist></mlt>", encoding="utf-8")
    assert nle_sync._clip_ranges(path, "mlt", 10.0)



def test_transcribe_model_kind_validation(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps import transcribe as transcribe_module

    context = _context(tmp_path)
    monkeypatch.setattr(
        "videoflow.application.models.list_models",
        lambda: [{"id": "x", "capability": "asr", "kind": "other", "installed": True}],
    )
    monkeypatch.setattr("videoflow.application.models.installed_path", lambda _id: tmp_path)
    with pytest.raises(VideoFlowError):
        transcribe_module.TranscribeStep().run(
            context,
            transcribe_module.TranscribeParams(model_id="x", mode="faster_whisper"),
            StepIO(),
        )
    monkeypatch.setattr(
        "videoflow.application.models.list_models",
        lambda: [{"id": "x", "capability": "llm", "kind": "local", "installed": True}],
    )
    with pytest.raises(VideoFlowError):
        transcribe_module.TranscribeStep().run(
            context,
            transcribe_module.TranscribeParams(model_id="x", mode="faster_whisper"),
            StepIO(),
        )
