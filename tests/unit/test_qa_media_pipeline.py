from __future__ import annotations

import json
from pathlib import Path

from videoflow.application import qa_media
from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.qa_media import (
    QaRepairParams,
    QaRepairStep,
    QaTranscriptParams,
    QaTranscriptStep,
)


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir()
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_detect_black_parses_spans(monkeypatch) -> None:
    monkeypatch.setattr(
        qa_media,
        "_run_filter",
        lambda video, filter_name: "black_start:1.0 black_end:1.4\nblack_start:5 black_end:5.2",
    )
    issues = qa_media.detect_black(Path("video.mp4"), min_duration=0.1)
    assert [item["kind"] for item in issues] == ["black_frame", "black_frame"]
    assert issues[0]["start_sec"] == 1.0


def test_detect_freeze_parses_spans(monkeypatch) -> None:
    monkeypatch.setattr(
        qa_media,
        "_run_filter",
        lambda video, filter_name: (
            "freeze_start: 2.5\nfreeze_end: 3.5\n"
            "freeze_start: 9\nfreeze_end: 10"
        ),
    )
    issues = qa_media.detect_freeze(Path("video.mp4"))
    assert [item["kind"] for item in issues] == ["static_screen", "static_screen"]
    assert issues[0]["end_sec"] == 3.5


def test_run_filter_without_ffmpeg(monkeypatch) -> None:
    monkeypatch.setattr(qa_media, "find_binary", lambda name: None)
    assert qa_media._run_filter(Path("video.mp4"), "blackdetect") == ""


def test_compare_text_reports_missing_and_extra() -> None:
    result = qa_media.compare_text("one two three", "one three four")
    assert 0 < result["similarity"] < 1
    assert "two" in result["missing"]
    assert "four" in result["extra"]
    assert result["passed"] is False


def test_compare_text_passes_identical_text() -> None:
    result = qa_media.compare_text("a b c", "a b c")
    assert result["passed"] is True
    assert result["similarity"] == 1.0


def test_transcript_audit_skips_without_reference(tmp_path: Path) -> None:
    context = _context(tmp_path)
    QaTranscriptStep().run(context, QaTranscriptParams(), StepIO())
    assert any("no script reference" in item for item in context.warnings)


def test_transcript_audit_skips_without_hypothesis(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (context.output / "script").mkdir(parents=True)
    (context.output / "script" / "narration.txt").write_text("hello", encoding="utf-8")
    QaTranscriptStep().run(context, QaTranscriptParams(), StepIO())
    assert any("no spoken transcript" in item for item in context.warnings)


def test_repair_plan_maps_issues_to_units(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (context.output / "qa").mkdir(parents=True)
    (context.output / "qa" / "frames.json").write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "kind": "black_frame",
                        "severity": "critical",
                        "start_sec": 1.0,
                        "message": "black",
                    }
                ]
            }
        )
    )
    (context.output / "qa" / "transcript.json").write_text(
        json.dumps({"passed": False, "similarity": 0.4})
    )
    (context.output / "storyboard").mkdir(parents=True)
    (context.output / "storyboard" / "units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "UNIT-0001",
                        "start_sec": 0,
                        "end_sec": 4,
                        "title": "Opening",
                    }
                ]
            }
        )
    )
    QaRepairStep().run(context, QaRepairParams(), StepIO())
    payload = json.loads((context.output / "qa" / "repair-plan.json").read_text())
    assert payload["count"] == 2
    assert {item["kind"] for item in payload["issues"]} == {
        "black_frame",
        "transcript_mismatch",
    }
    assert payload["issues"][0]["unit_id"] == "UNIT-0001"
