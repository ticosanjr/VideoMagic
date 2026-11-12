from __future__ import annotations

from pathlib import Path

from videoflow.application import voice_clone
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import CapabilityUnavailableError
from videoflow.steps.base import StepIO
from videoflow.steps.voice_clone import VoiceCloneParams, VoiceCloneStep


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir()
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
        metadata={
            "hilt_answers": {
                "answers": {
                    "voice_profile_id": "voice-123",
                    "voice_text": "corrected line",
                }
            }
        },
    )


def test_voice_clone_writes_the_repair_patch(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    calls: list[object] = []

    def fake_synthesize(request):
        calls.append(request)
        return b"mp3-bytes"

    monkeypatch.setattr(voice_clone, "synthesize", fake_synthesize)
    VoiceCloneStep().run(context, VoiceCloneParams(), StepIO())

    assert calls
    target = context.output / "audio" / "voice-patch.mp3"
    assert target.read_bytes() == b"mp3-bytes"
    assert context.metadata["voice_clone_patch"]["profile_id"] == "voice-123"
    assert context.artifacts["voice_clone_patch"] == str(target)


def test_voice_clone_skips_when_a_human_patch_exists(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    (context.output / "audio").mkdir()
    (context.output / "audio" / "voice-patch.wav").write_bytes(b"human")
    monkeypatch.setattr(
        voice_clone,
        "synthesize",
        lambda request: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    VoiceCloneStep().run(context, VoiceCloneParams(), StepIO())

    assert context.artifacts.get("voice_clone_patch") is None


def test_voice_clone_warns_when_unavailable(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)

    def unavailable(request):
        raise CapabilityUnavailableError("voice_clone", "not configured")

    monkeypatch.setattr(voice_clone, "synthesize", unavailable)
    VoiceCloneStep().run(context, VoiceCloneParams(), StepIO())

    assert any("Voice clone unavailable" in item for item in context.warnings)
    assert context.artifacts.get("voice_clone_patch") is None
