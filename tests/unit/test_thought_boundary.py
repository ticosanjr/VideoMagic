from __future__ import annotations

from videoflow.application.shorts import select_shorts
from videoflow.application.thought_boundary import enforce_thought_boundary
from videoflow.domain.state import Sentence

RATE = 48_000


def sentence(identifier: int, text: str, start: int, end: int) -> Sentence:
    return Sentence(id=identifier, start_sample=start, end_sample=end, text=text)


def test_extends_to_the_next_complete_thought() -> None:
    sentences = [
        sentence(0, "Hoje eu vou mostrar como", 0, 2 * RATE),
        sentence(1, "instalar o programa no computador.", 2 * RATE, 5 * RATE),
    ]
    result = enforce_thought_boundary(sentences, 0, 3 * RATE, sample_rate=RATE)
    assert result.adjusted is True
    assert result.end_sample == 5 * RATE
    assert result.boundary_sentence_id == 1


def test_retracts_to_the_previous_complete_thought() -> None:
    sentences = [
        sentence(0, "Primeira ideia completa.", 0, 2 * RATE),
        sentence(1, "Segunda ideia que ainda", 3 * RATE, 5 * RATE),
    ]
    result = enforce_thought_boundary(sentences, 0, 4 * RATE, sample_rate=RATE)
    assert result.adjusted is True
    assert result.end_sample == 2 * RATE
    assert result.boundary_sentence_id == 0


def test_rejects_a_dangling_terminal_word() -> None:
    sentences = [
        sentence(0, "Vamos falar sobre isso e.", 0, 2 * RATE),
        sentence(1, "Outra ideia completa.", 10 * RATE, 12 * RATE),
    ]
    result = enforce_thought_boundary(sentences, 0, 2 * RATE, sample_rate=RATE)
    assert result.adjusted is False
    assert result.end_sample == 2 * RATE


def test_no_terminal_sentence_keeps_the_original_end() -> None:
    sentences = [sentence(0, "uma frase sem fim", 0, 2 * RATE)]
    result = enforce_thought_boundary(sentences, 0, 2 * RATE, sample_rate=RATE)
    assert result.adjusted is False
    assert result.end_sample == 2 * RATE


def test_select_shorts_applies_the_boundary() -> None:
    sentences = [
        sentence(0, "Hoje eu vou mostrar como", 0, 2 * RATE),
        sentence(1, "instalar o programa no computador.", 2 * RATE, 5 * RATE),
    ]
    clips = select_shorts(
        sentences,
        min_samples=RATE,
        max_samples=3 * RATE,
        count=1,
        sample_rate=RATE,
        thought_boundary=True,
    )
    assert clips
    assert clips[0].end_sample == 5 * RATE


def test_select_shorts_can_disable_the_boundary() -> None:
    sentences = [
        sentence(0, "Hoje eu vou mostrar como", 0, 2 * RATE),
        sentence(1, "instalar o programa no computador.", 2 * RATE, 5 * RATE),
    ]
    clips = select_shorts(
        sentences,
        min_samples=RATE,
        max_samples=3 * RATE,
        count=1,
        sample_rate=RATE,
        thought_boundary=False,
    )
    assert clips
    assert clips[0].end_sample == 2 * RATE
