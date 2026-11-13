from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.factcheck import FactcheckAuditStep, FactcheckParams
from videoflow.steps.voice_patch import VoicePatchParams, VoicePatchStep


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    (output / "research").mkdir(parents=True)
    (output / "script").mkdir(parents=True)
    (output / "audio").mkdir(parents=True)
    (output / "research" / "master.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "title": "Case",
                        "sources": [{"url": "https://example.com/source", "title": "Source"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (output / "script" / "script.json").write_text(
        json.dumps(
            {
                "sections": [
                    {
                        "title": "Case",
                        "narration": "In 2014, Nestor Cerveró cited R$ 1 milhão.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (output / "audio" / "master.wav").write_bytes(b"RIFF")
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
        artifacts={"audio_mix": str(output / "audio" / "master.wav")},
    )


def test_factcheck_fallback_extracts_claims(tmp_path: Path) -> None:
    context = _context(tmp_path)
    FactcheckAuditStep().run(context, FactcheckParams(), StepIO())
    report = context.metadata["factcheck"]
    assert report["generated_by"] == "deterministic"
    assert report["claims"]
    assert any(item["kind"] == "date" for item in report["claims"])


def test_factcheck_llm_drops_invented_sources(tmp_path: Path) -> None:
    class Llm:
        def complete_json(self, prompt: str, schema: str) -> dict:
            return {
                "claims": [
                    {
                        "claim": "Nestor Cerveró cited the evidence",
                        "status": "supported",
                        "note": "ok",
                        "sources": [
                            {"url": "https://example.com/source"},
                            {"url": "https://invented.example/source"},
                        ],
                    }
                ],
                "summary": "one claim",
            }

    context = _context(tmp_path)
    FactcheckAuditStep().run(context, FactcheckParams(), StepIO(llm_client=Llm()))
    report = context.metadata["factcheck"]
    assert report["generated_by"] == "llm"
    assert len(report["claims"][0]["sources"]) == 1
    assert report["claims"][0]["sources"][0]["url"] == "https://example.com/source"


def test_voice_patch_skips_without_a_patch(tmp_path: Path) -> None:
    context = _context(tmp_path)
    VoicePatchStep().run(context, VoicePatchParams(), StepIO())
    assert any("no patch" in warning.lower() for warning in context.warnings)


def test_voice_patch_splices_and_updates_the_master(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    patch = context.output / "audio" / "voice-patch.wav"
    patch.write_bytes(b"RIFF")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"RIFF-repaired")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("videoflow.steps.voice_patch.subprocess.run", fake_run)
    context.metadata["hilt_answers"] = {
        "answers": {"patch_start_sec": 1.0, "patch_end_sec": 2.0}
    }
    VoicePatchStep().run(context, VoicePatchParams(), StepIO())
    assert commands
    assert "[pre]" in ";".join(commands[0])
    assert "[patch]" in ";".join(commands[0])
    assert Path(context.artifacts["voice_patch"]).is_file()
    assert (context.output / "audio" / "master.wav").read_bytes() == b"RIFF-repaired"


def test_voice_patch_missing_master_and_alternative_suffix(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    context.artifacts.pop("audio_mix", None)
    VoicePatchStep().run(context, VoicePatchParams(), StepIO())
    assert any("no final audio" in item for item in context.warnings)

    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF")
    context.artifacts["audio_master"] = str(master)
    patch = context.output / "audio" / "voice-patch.mp3"
    patch.write_bytes(b"MP3")
    monkeypatch.setattr(
        "videoflow.steps.voice_patch.subprocess.run",
        lambda command, **kwargs: (
            Path(command[-1]).write_bytes(b"repaired"),
            SimpleNamespace(returncode=0, stderr=""),
        )[1],
    )
    VoicePatchStep().run(
        context,
        VoicePatchParams(start_sec=0, end_sec=1),
        StepIO(),
    )
    assert context.artifacts["voice_patch"]

    monkeypatch.setattr(
        "videoflow.steps.voice_patch.first_provider",
        lambda capability: {"base_url": "http://127.0.0.1:1/v1"},
    )
    monkeypatch.setattr(
        "videoflow.steps.voice_patch.OpenAITtsAdapter",
        lambda **kwargs: SimpleNamespace(
            synthesize=lambda text, target: (Path(target).write_bytes(b"tts") or target)
        ),
    )
    synth = VoicePatchStep._tts_patch(context, "hello", StepIO())
    assert synth is not None and synth.is_file()


def test_voice_patch_unavailable_tts_and_ffmpeg_errors(
    tmp_path: Path, monkeypatch
) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr("videoflow.steps.voice_patch.first_provider", lambda capability: None)
    assert VoicePatchStep._tts_patch(context, "hello", StepIO()) is None

    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF")
    context.artifacts["audio_master"] = str(master)
    patch = context.output / "audio" / "voice-patch.wav"
    patch.write_bytes(b"RIFF")
    monkeypatch.setattr("videoflow.steps.voice_patch.find_binary", lambda name: None)
    import pytest

    with pytest.raises(RuntimeError):
        VoicePatchStep().run(context, VoicePatchParams(start_sec=0, end_sec=1), StepIO())

    monkeypatch.setattr("videoflow.steps.voice_patch.find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        "videoflow.steps.voice_patch.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(returncode=1, stderr="bad"),
    )
    with pytest.raises(RuntimeError, match="Voice repair failed"):
        VoicePatchStep().run(context, VoicePatchParams(start_sec=0, end_sec=1), StepIO())


def test_voice_patch_invalid_segment_and_optional_fallbacks(
    tmp_path: Path, monkeypatch
) -> None:
    from videoflow.domain.state import MediaInfo

    context = _context(tmp_path)
    context.media = MediaInfo(
        source_path=str(context.source),
        duration_frames=0,
        fps_num=30,
        fps_den=1,
        width=1280,
        height=720,
        audio_sample_rate=48000,
    )
    master = context.output / "audio" / "master.wav"
    master.parent.mkdir(parents=True, exist_ok=True)
    master.write_bytes(b"RIFF")
    context.artifacts["audio_mix"] = str(master)
    patch = context.output / "audio" / "voice-patch.wav"
    patch.write_bytes(b"RIFF")
    VoicePatchStep().run(
        context, VoicePatchParams(start_sec=1, end_sec=2), StepIO()
    )
    assert any("invalid segment" in item for item in context.warnings)

    monkeypatch.setattr(
        "videoflow.steps.voice_patch.first_provider",
        lambda capability: {"base_url": ""},
    )
    assert VoicePatchStep._tts_patch(context, "hello", StepIO()) is None
    monkeypatch.setattr(
        "videoflow.steps.voice_patch.first_provider",
        lambda capability: {"base_url": "http://127.0.0.1:1/v1"},
    )
    monkeypatch.setattr(
        "videoflow.steps.voice_patch.OpenAITtsAdapter",
        lambda **kwargs: SimpleNamespace(
            synthesize=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("tts down"))
        ),
    )
    assert VoicePatchStep._tts_patch(context, "hello", StepIO()) is None
    assert any("TTS voice patch fallback" in item for item in context.warnings)
    assert VoicePatchStep().cache_outputs(context) == ()
