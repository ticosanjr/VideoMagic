from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.core.context import PipelineContext
from videoflow.domain.state import Sentence, WordTiming
from videoflow.steps.base import StepIO
from videoflow.steps.llm_cleanup import CleanupParams, LlmCleanupStep


class FakeClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.prompt = ""

    def complete_json(self, prompt: str, schema_name: str) -> dict[str, Any]:
        self.prompt = prompt
        return self.response


def _sentence(identifier: int, text: str) -> Sentence:
    return Sentence(
        id=identifier,
        start_sample=identifier * 48_000,
        end_sample=(identifier + 1) * 48_000,
        text=text,
        words=[
            WordTiming(
                word=text.split()[0],
                start_sample=identifier * 48_000,
                end_sample=(identifier + 1) * 48_000,
                probability=0.9,
            )
        ],
    )


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir()
    work = output / "work"
    exports = output / "exports"
    work.mkdir()
    exports.mkdir()
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=work,
        exports=exports,
    )
    context.source.write_bytes(b"x")
    context.transcript = [
        _sentence(0, "Hostgator apoia esse vídeo e tem oferta."),
        _sentence(1, "Tem mosca aqui."),
        _sentence(
            2,
            "O modelo foi lançado com uma arquitetura nova e vários detalhes "
            "técnicos importantes para programadores.",
        ),
        _sentence(3, "O preço é 10 dólares por milhão de tokens."),
    ]
    return context


def test_cleanup_removes_only_the_short_aside(tmp_path: Path) -> None:
    context = _context(tmp_path)
    client = FakeClient(
        {"discard_sentence_ids": [0, 1, 2, 3], "reasoning": "asides"}
    )
    LlmCleanupStep().run(
        context,
        CleanupParams(provider_id="deepseek", max_words=10),
        StepIO(llm_client=client),
    )
    assert context.discard_sentence_ids == [1]
    report = context.metadata["cleanup_report"]
    assert report["discarded_sentence_ids"] == [1]
    protected = {item["sentence_id"] for item in report["rejected"]}
    assert protected == {0, 2, 3}
    assert "Tem mosca aqui" in client.prompt


def test_cleanup_skips_without_a_provider(tmp_path: Path) -> None:
    context = _context(tmp_path)
    LlmCleanupStep().run(context, CleanupParams(), StepIO(llm_client=None))
    assert context.discard_sentence_ids == []
    assert context.metadata["cleanup_report"]["reasoning"].startswith("skipped")


def test_cleanup_does_nothing_without_a_transcript(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript = []
    LlmCleanupStep().run(
        context,
        CleanupParams(),
        StepIO(llm_client=FakeClient({"discard_sentence_ids": [1]})),
    )
    assert context.metadata["cleanup_report"]["reasoning"] == "no transcript"


def test_cleanup_rejects_invalid_long_protected_and_all(tmp_path: Path) -> None:
    context = _context(tmp_path)
    client = FakeClient(
        {
            "discard_sentence_ids": [999, 2, 3, 0, 1],
            "reasoning": "everything",
        }
    )
    LlmCleanupStep().run(
        context,
        CleanupParams(provider_id="deepseek", max_words=10, max_cuts=10),
        StepIO(llm_client=client),
    )
    report = context.metadata["cleanup_report"]
    rejected = {item["sentence_id"] for item in report["rejected"]}
    assert 999 in rejected
    assert 2 in rejected
    assert 3 in rejected
    assert report["discarded_sentence_ids"] == [1]


def test_cleanup_keeps_at_least_one_sentence(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.transcript = [_sentence(0, "Tem mosca aqui.")]
    LlmCleanupStep().run(
        context,
        CleanupParams(provider_id="deepseek", max_words=10),
        StepIO(llm_client=FakeClient({"discard_sentence_ids": [0]})),
    )
    assert context.discard_sentence_ids == []
    assert context.metadata["cleanup_report"]["discarded_sentence_ids"] == []
