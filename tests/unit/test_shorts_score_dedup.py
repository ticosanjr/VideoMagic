"""Regression: LLM Short rankings must not duplicate a clip."""

from __future__ import annotations

from videoflow.application.shorts import ShortClip
from videoflow.steps.base import StepIO
from videoflow.steps.shorts_score import ShortsScoreStep


class FakeLlm:
    def __init__(self, ranking: object) -> None:
        self.ranking = ranking

    def complete_json(self, prompt: str, schema: str) -> dict[str, object]:
        return {"ranking": self.ranking}


def clip(title: str) -> ShortClip:
    return ShortClip(title, 0, 48000, (0,), ((0, 48000),))


def test_repeated_ranking_indices_are_ignored() -> None:
    clips = [clip("a"), clip("b")]

    ordered = ShortsScoreStep()._llm_rerank(
        clips, StepIO(llm_client=FakeLlm([1, 1, 0]))
    )

    assert [item.title for item in ordered] == ["b", "a"]


def test_invalid_indices_and_missing_clips_are_appended_once() -> None:
    clips = [clip("a"), clip("b"), clip("c")]

    ordered = ShortsScoreStep()._llm_rerank(
        clips, StepIO(llm_client=FakeLlm([2, 99, -1, "x"]))
    )

    assert [item.title for item in ordered] == ["c", "a", "b"]
