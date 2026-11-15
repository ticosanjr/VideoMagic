"""Branch coverage for headless tools, transcribe fallbacks, and sync."""

from __future__ import annotations

import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import render_gate as render_gate_module
from videoflow.application import sync
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.state import MediaInfo
from videoflow.mcp_server.tools_headless import register_headless_tools
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


def _tools(tmp: Path, monkeypatch) -> dict[str, object]:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp / "home"))
    context = _context(tmp)
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

    register_headless_tools(register, FakeContext())
    return tools


def test_headless_tool_error_branches(tmp_path: Path, monkeypatch) -> None:
    tools = _tools(tmp_path, monkeypatch)
    assert tools["vf_beatmap_execute"](manifest={"metadata": {}})["ok"] is False
    assert (
        tools["vf_beatmap_execute"](
            manifest={"metadata": {"source": str(tmp_path / "source.mp4")}},
            recipe_id="missing",
        )["ok"]
        is False
    )
    assert tools["vf_preview_archetypes"](job_id="missing")["ok"] is False
    assert tools["vf_web_scene_preview"](root=str(tmp_path / "missing"))["ok"] is False
    assert tools["vf_audio_patch_line"](text="")["ok"] is False
    assert tools["vf_preset_rules"](channel_id="x", action="bad")["ok"] is False
    assert tools["vf_style_clone"](channel_id="x")["ok"] is True


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


def test_render_gate_without_fcntl(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(render_gate_module, "fcntl", None)
    gate = render_gate_module.RenderGate(path=tmp_path / "lock")
    with gate.hold("test"):
        pass
    assert gate.status()["cross_process"] is False
