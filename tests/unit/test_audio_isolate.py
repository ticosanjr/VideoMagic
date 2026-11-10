from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.steps import audio_isolate as isolate_module
from videoflow.steps.audio_isolate import AudioIsolateStep, IsolateParams
from videoflow.steps.base import StepIO


def _context(tmp_path: Path) -> PipelineContext:
    source = tmp_path / "source.wav"
    source.write_bytes(b"RIFF")
    return PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        pcm_path=source,
    )


def test_voice_isolation_falls_back_to_master(tmp_path: Path) -> None:
    context = _context(tmp_path)
    AudioIsolateStep().run(
        context,
        IsolateParams(backend="none", fallback_to_master=True),
        StepIO(),
    )
    target = Path(context.artifacts["audio_isolated"])
    assert target.is_file()
    assert target.read_bytes() == b"RIFF"
    assert context.metadata["audio_isolated"]["backend"] == "master"
    assert context.warnings


def test_voice_isolation_uses_rnnoise_when_available(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    model = tmp_path / "model.rnnn"
    model.write_bytes(b"model")

    def fake_run(command, timeout=1800):
        Path(command[-1]).write_bytes(b"isolated")
        return True

    monkeypatch.setattr(isolate_module, "find_binary", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(isolate_module, "_run", fake_run)
    AudioIsolateStep().run(
        context,
        IsolateParams(backend="rnnoise", model_path=str(model)),
        StepIO(),
    )
    assert Path(context.artifacts["audio_isolated"]).read_bytes() == b"isolated"
    assert context.metadata["audio_isolated"]["backend"] == "rnnoise"
