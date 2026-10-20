import pytest

from videoflow.application.shorts import (
    build_ass,
    select_shorts,
    sentence_events,
    slugify,
)
from videoflow.domain.errors import InvalidRetakeIdsError
from videoflow.domain.state import Sentence

RATE = 48000


def sentence(item_id: int, start_sec: int, end_sec: int, text: str | None = None) -> Sentence:
    return Sentence(
        id=item_id,
        start_sample=start_sec * RATE,
        end_sample=end_sec * RATE,
        text=text or f"line {item_id}",
    )


def test_deterministic_windows_are_non_overlapping_and_bounded() -> None:
    sentences = [sentence(index, index * 10, (index + 1) * 10) for index in range(4)]
    clips = select_shorts(
        sentences,
        min_samples=10 * RATE,
        max_samples=25 * RATE,
        count=2,
        sample_rate=RATE,
    )
    assert len(clips) == 2
    assert (clips[0].start_sample, clips[0].end_sample) == (0, 20 * RATE)
    assert (clips[1].start_sample, clips[1].end_sample) == (20 * RATE, 40 * RATE)
    assert clips[0].duration_samples == 20 * RATE


def test_cuts_can_drop_a_window_below_the_minimum() -> None:
    sentences = [sentence(0, 0, 30)]
    clips = select_shorts(
        sentences,
        min_samples=25 * RATE,
        max_samples=40 * RATE,
        count=1,
        sample_rate=RATE,
        cuts=[(5 * RATE, 15 * RATE)],
    )
    assert clips == []


def test_no_usable_window_reports_a_warning() -> None:
    warnings: list[str] = []
    clips = select_shorts(
        [sentence(0, 0, 5)],
        min_samples=10 * RATE,
        max_samples=30 * RATE,
        count=1,
        sample_rate=RATE,
        warnings=warnings,
    )
    assert clips == []
    assert warnings


def test_llm_window_is_validated_and_used() -> None:
    sentences = [sentence(0, 0, 10), sentence(1, 10, 20)]

    class Client:
        def complete_json(self, prompt: str, schema_name: str) -> dict:
            assert "sentence_ids" in prompt
            return {"clips": [{"title": "The hook", "sentence_ids": [0, 1]}], "reasoning": "ok"}

    clips = select_shorts(
        sentences,
        min_samples=10 * RATE,
        max_samples=30 * RATE,
        count=1,
        sample_rate=RATE,
        client=Client(),  # type: ignore[arg-type]
    )
    assert len(clips) == 1
    assert clips[0].title == "The hook"
    assert clips[0].pieces == ((0, 20 * RATE),)


def test_llm_unknown_id_is_rejected() -> None:
    class Client:
        def complete_json(self, prompt: str, schema_name: str) -> dict:
            return {"clips": [{"title": "bad", "sentence_ids": [9]}], "reasoning": "x"}

    with pytest.raises(InvalidRetakeIdsError):
        select_shorts(
            [sentence(0, 0, 10)],
            min_samples=1,
            max_samples=20 * RATE,
            count=1,
            sample_rate=RATE,
            client=Client(),  # type: ignore[arg-type]
        )


def test_ass_times_and_text_are_escaped() -> None:
    ass = build_ass([(0, 1.25, "hello {world}"), (3661.5, 3662, "line\\two")])
    assert "0:00:01.25" in ass
    assert "1:01:01.50" in ass
    assert "hello (world)" in ass
    assert "line\\\\two" in ass


def test_sentence_events_follow_concatenated_pieces() -> None:
    sentences = [sentence(0, 0, 2), sentence(1, 4, 6)]
    events = sentence_events(sentences, [(0, 1 * RATE), (1 * RATE, 2 * RATE)], sample_rate=RATE)
    # The first sentence is split across the two pieces; both events start at 0.
    assert events[0][0] == 0
    assert events[0][1] == 1
    assert events[1][0] == 1
    assert events[1][1] == 2


def test_slug_is_safe_and_indexed() -> None:
    assert slugify("The Hook: AI & You!", 1) == "01-the-hook-ai-you"
    assert slugify("", 2) == "02-short"
