from __future__ import annotations

from videoflow.application.takes import (
    segment_takes,
    select_duplicate_takes,
)
from videoflow.domain.state import Sentence


def sentence(item_id: int, text: str, start: float, end: float) -> Sentence:
    return Sentence(
        id=item_id,
        text=text,
        start_sample=int(start * 48_000),
        end_sample=int(end * 48_000),
    )


def test_segment_takes_splits_at_a_long_pause() -> None:
    sentences = [
        sentence(0, "Primeira frase completa.", 0.0, 2.0),
        sentence(1, "Segunda frase completa.", 2.0, 4.0),
        sentence(2, "Outra frase depois da pausa.", 6.0, 8.0),
    ]
    takes = segment_takes(sentences, max_pause_ms=1200)
    assert [take.sentence_ids for take in takes] == [(0, 1), (2,)]


def test_segment_takes_splits_at_a_restart() -> None:
    sentences = [
        sentence(0, "O modelo novo chegou e mudou tudo.", 0.0, 2.0),
        sentence(1, "O modelo novo chegou e mudou completamente o jogo.", 2.5, 5.0),
    ]
    takes = segment_takes(sentences)
    assert [take.sentence_ids for take in takes] == [(0,), (1,)]


def test_duplicate_takes_keep_the_later_complete_attempt() -> None:
    sentences = [
        sentence(0, "O modelo novo chegou e mudou o jogo.", 0.0, 2.0),
        sentence(1, "O modelo novo chegou e mudou completamente o jogo.", 3.0, 5.5),
    ]
    groups = select_duplicate_takes(sentences)
    assert groups
    assert groups[0].keep == (1,)
    assert groups[0].discard == (0,)


def test_duplicate_takes_restore_a_unique_number() -> None:
    sentences = [
        sentence(0, "O modelo marcou 92,7% no teste.", 0.0, 2.0),
        sentence(1, "O modelo marcou 91,2% no teste.", 3.0, 5.0),
    ]
    groups = select_duplicate_takes(sentences)
    assert not groups


def test_unrelated_takes_are_not_grouped() -> None:
    sentences = [
        sentence(0, "O modelo novo chegou e mudou o jogo.", 0.0, 2.0),
        sentence(1, "A empresa abriu o código para todo mundo.", 3.0, 5.0),
    ]
    assert select_duplicate_takes(sentences) == ()


def test_semantic_duplicate_sentences_discards_covered_earlier_line(monkeypatch) -> None:
    import numpy as np

    from videoflow.application import semantic
    from videoflow.application.takes import semantic_duplicate_sentences

    sentences = [
        sentence(0, "O modelo novo chegou.", 0.0, 2.0),
        sentence(1, "O modelo novo chegou e mudou o jogo.", 3.0, 5.0),
    ]
    monkeypatch.setattr(semantic, "available", lambda: True)
    monkeypatch.setattr(
        semantic,
        "encode",
        lambda _texts: np.asarray([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32),
    )
    assert semantic_duplicate_sentences(sentences, set()) == {0}
