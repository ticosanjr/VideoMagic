"""Retake helpers: empty input, merge overlap, windowing, and reports."""

from __future__ import annotations

from videoflow.application.retakes import RetakeResult, _merge, _windows, cull_retakes
from videoflow.domain.state import Sentence


def sentence(item_id: int) -> Sentence:
    return Sentence(
        id=item_id,
        start_sample=item_id * 48000,
        end_sample=(item_id + 1) * 48000,
        text=f"line {item_id}",
    )


def test_empty_transcript_returns_an_empty_result() -> None:
    result = cull_retakes([])

    assert result.discard_sentence_ids == ()
    assert result.windows == 0


def test_result_dict_is_json_friendly() -> None:
    payload = RetakeResult((1, 2), (3,), "reason", 2).to_dict()

    assert payload == {
        "discard_sentence_ids": [1, 2],
        "restored_sentence_ids": [3],
        "reasoning": "reason",
        "windows": 2,
    }


def test_merge_combines_overlapping_and_touching_spans() -> None:
    assert _merge([(5, 10), (0, 2), (1, 3), (10, 12), (20, 20)]) == [
        (0, 3),
        (5, 12),
    ]


def test_windows_cover_the_transcript_with_overlap() -> None:
    sentences = [sentence(index) for index in range(5)]

    assert _windows(sentences, 10) == [sentences]
    chunks = _windows(sentences, 2)
    assert chunks[0] == sentences[:2]
    assert chunks[-1][-1] == sentences[-1]
    assert len(chunks) > 1
