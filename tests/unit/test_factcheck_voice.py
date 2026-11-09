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
