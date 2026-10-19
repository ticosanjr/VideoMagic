import pytest

from videoflow.application.retakes import (
    cull_intervals,
    cull_retakes,
    subtract_spans,
)
from videoflow.domain.errors import InvalidRetakeIdsError
from videoflow.domain.state import Sentence


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def complete_json(self, prompt: str, schema_name: str) -> dict:
        self.prompts.append(prompt)
        return self.responses.pop(0)


def sentence(item_id: int, text: str, start: int, end: int) -> Sentence:
    return Sentence(id=item_id, start_sample=start, end_sample=end, text=text)


def test_llm_discard_of_the_last_take_is_restored() -> None:
    sentences = [sentence(0, "Take one", 0, 1000), sentence(1, "Take one", 1000, 2000)]
    client = FakeClient([{"discard_sentence_ids": [0, 1], "reasoning": "all attempts"}])
    result = cull_retakes(sentences, client=client)
    assert result.discard_sentence_ids == (0,)
    assert result.restored_sentence_ids == (1,)


def test_unknown_ids_are_rejected() -> None:
    sentences = [sentence(0, "one", 0, 1000)]
    client = FakeClient([{"discard_sentence_ids": [9], "reasoning": "bad"}])
    with pytest.raises(InvalidRetakeIdsError):
        cull_retakes(sentences, client=client)


def test_without_a_client_exact_repeats_are_culled() -> None:
    sentences = [
        sentence(0, "Same line.", 0, 1000),
        sentence(1, "  same line ", 1000, 2000),
        sentence(2, "Different.", 2000, 3000),
    ]
    result = cull_retakes(sentences)
    assert result.discard_sentence_ids == (0,)
    assert result.windows == 0


def test_large_transcripts_use_overlapping_windows() -> None:
    sentences = [
        sentence(index, f"line {index}", index * 1000, (index + 1) * 1000) for index in range(10)
    ]
    client = FakeClient([{"discard_sentence_ids": [], "reasoning": "ok"} for _ in range(6)])
    result = cull_retakes(sentences, client=client, context_window=4)
    assert result.windows >= 3
    assert len(client.prompts) == result.windows


def test_interval_subtraction() -> None:
    assert subtract_spans([(0, 100), (200, 300)], [(50, 250)]) == [(0, 50), (250, 300)]
    assert subtract_spans([(0, 100)], [(0, 100)]) == []
    assert cull_intervals([sentence(0, "a", 10, 20), sentence(1, "b", 30, 40)], [0]) == [(10, 20)]
