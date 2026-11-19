from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.decupage import Asu, AsuWord
from videoflow.steps.base import StepIO
from videoflow.steps.decupage_review import (
    ApplyParams,
    DecupageApplyStep,
    DecupageLlmStep,
    DecupagePrefilterStep,
    LlmParams,
)


def _word(index: int, text: str, start: int, end: int) -> AsuWord:
    return AsuWord(
        idx=index,
        w=text,
        start_sample=start,
        end_sample=end,
        start_sec=start / 16_000,
        end_sec=end / 16_000,
        p=0.9,
    )


def _asu(
    identifier: int,
    text: str,
    start: int,
    *,
    stutter: bool = False,
    noise: list[dict] | None = None,
) -> Asu:
    words = text.split()
    step = max(1, 800 // max(1, len(words)))
    return Asu(
        asu_id=f"ASU_{identifier:04d}",
        start_sample=start,
        end_sample=start + 800,
        start_sec=start / 16_000,
        end_sec=(start + 800) / 16_000,
        text=text,
        avg_word_prob=0.9,
        has_stutter_candidate=stutter,
        noise_events=noise or [],
        words=[
            _word(index, word, start + index * step, start + (index + 1) * step)
            for index, word in enumerate(words)
        ],
    )


def _context(tmp_path: Path, asus: list[Asu]) -> PipelineContext:
    return PipelineContext(
        source=tmp_path / "source.wav",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        metadata={"asus": [item.model_dump(mode="json") for item in asus]},
    )


def test_prefilter_groups_retakes_and_quarantines_noise(tmp_path: Path) -> None:
    context = _context(
        tmp_path,
        [
            _asu(1, "Hoje a gente vai configurar o Docker.", 0),
            _asu(2, "Hoje a gente vai configurar o Docker agora.", 1000),
            _asu(
                3,
                "Cof cof",
                2000,
                noise=[{"label": "Cough", "start_sample": 2000, "end_sample": 2800, "score": 0.9}],
            ),
        ],
    )
    DecupagePrefilterStep().run(context, {}, StepIO())
    asus = context.metadata["asus"]
    assert asus[0]["retake_group_id"] == "RG_0001"
    assert asus[1]["retake_group_id"] == "RG_0001"
    decisions = context.metadata["decupage_prefilter_decisions"]
    assert any(item["category"] == "NOISE" for item in decisions)
    assert Path(context.artifacts["decupage_prefilter"]).is_file()


def test_llm_caller_writes_request_without_calling_a_model(tmp_path: Path) -> None:
    context = _context(tmp_path, [_asu(1, "Uma frase completa.", 0)])
    DecupageLlmStep().run(
        context,
        LlmParams(llm_policy="caller", mode="pass1"),
        StepIO(),
    )
    contract = context.metadata["decupage_llm"]
    assert contract["required"] is True
    assert contract["policy"] == "caller"
    assert contract["status"] == "waiting"
    request = json.loads(Path(context.artifacts["decupage_llm_request"]).read_text())
    assert request["schema"] == "decupage_decisions_v1"
    assert "windows" in request
    assert "start_sec" not in json.dumps(request["windows"])


def test_llm_videoflow_records_decisions(tmp_path: Path) -> None:
    context = _context(tmp_path, [_asu(1, "Uma frase completa.", 0)])

    class Client:
        def complete_json(self, prompt: str, schema: str) -> dict:
            assert "ASU_0001" in prompt
            return {
                "decisions": [
                    {
                        "asu_id": "ASU_0001",
                        "action": "KEEP",
                        "category": "REVIEW",
                        "confidence": 0.6,
                        "reason": "keep for safety",
                    }
                ]
            }

    DecupageLlmStep().run(
        context,
        LlmParams(llm_policy="videoflow", mode="pass1"),
        StepIO(llm_client=Client()),
    )
    assert context.metadata["decupage_llm"]["status"] == "done"
    assert context.metadata["decupage_llm"]["calls_made"] == 1
    assert context.metadata["decupage_decisions"][0]["action"] == "KEEP"
    assert Path(context.artifacts["decupage_decisions"]).is_file()


def test_apply_removes_and_trims_without_mutating_timeline(tmp_path: Path) -> None:
    context = _context(
        tmp_path,
        [
            _asu(1, "manter", 0),
            _asu(2, "remover", 1000),
            _asu(3, "eu eu configurar", 2000, stutter=True),
        ],
    )
    DecupageApplyStep().run(
        context,
        ApplyParams(
            decisions=[
                {"asu_id": "ASU_0002", "action": "REMOVE", "category": "RETAKE"},
                {
                    "asu_id": "ASU_0003",
                    "action": "TRIM_WORDS",
                    "remove_word_indices": [0],
                    "category": "STUTTER",
                },
            ]
        ),
        StepIO(),
    )
    assert context.metadata["decupage_state"]["removed"] == 1
    assert context.metadata["decupage_state"]["trimmed"] == 1
    assert [item["asu_id"] for item in context.metadata["asus"]] == ["ASU_0001", "ASU_0003"]
    assert context.metadata["asus"][-1]["text"] == "eu configurar"
    assert Path(context.artifacts["decupage_state"]).is_file()


def test_apply_restore_cancels_a_removal(tmp_path: Path) -> None:
    context = _context(tmp_path, [_asu(1, "manter", 0), _asu(2, "restaurar", 1000)])
    DecupageApplyStep().run(
        context,
        ApplyParams(
            decisions=[
                {"asu_id": "ASU_0002", "action": "REMOVE", "category": "RETAKE"},
                {"asu_id": "ASU_0002", "action": "RESTORE", "category": "CONTINUITY"},
            ]
        ),
        StepIO(),
    )
    assert [item["asu_id"] for item in context.metadata["asus"]] == [
        "ASU_0001",
        "ASU_0002",
    ]
    assert context.metadata["decupage_review_flags"]


def test_llm_none_is_explicit(tmp_path: Path) -> None:
    context = _context(tmp_path, [_asu(1, "Uma frase.", 0)])
    DecupageLlmStep().run(
        context,
        LlmParams(llm_policy="none"),
        StepIO(),
    )
    assert context.metadata["decupage_llm"]["status"] == "skipped"
    assert context.metadata["decupage_llm"]["required"] is False
