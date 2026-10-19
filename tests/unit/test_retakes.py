from typing import cast

import pytest

from videoflow.domain.errors import InvalidRetakeIdsError
from videoflow.domain.retakes import (
    RepetitionCluster,
    apply_retake_guard,
    cluster_exact_repetitions,
    normalize_sentence_text,
)


def test_cluster_rejects_empty_and_duplicate_ids() -> None:
    with pytest.raises(ValueError):
        RepetitionCluster(())
    with pytest.raises(ValueError):
        RepetitionCluster((1, 1))


def test_guard_restores_the_last_take_when_the_model_drops_everything() -> None:
    result = apply_retake_guard(
        [3, 4, 5],
        clusters=[RepetitionCluster((3, 4, 5))],
        valid_ids=[1, 2, 3, 4, 5],
    )
    assert result.discard_sentence_ids == (3, 4)
    assert result.restored_sentence_ids == (5,)
    assert "keep_last" in result.reasoning


def test_guard_leaves_a_legal_cull_alone() -> None:
    result = apply_retake_guard(
        [4],
        clusters=[RepetitionCluster((3, 4, 5))],
        valid_ids=[3, 4, 5],
    )
    assert result.discard_sentence_ids == (4,)
    assert result.restored_sentence_ids == ()
    assert result.reasoning == "no keeper was discarded"


def test_guard_rejects_unknown_ids_without_partial_application() -> None:
    with pytest.raises(InvalidRetakeIdsError) as caught:
        apply_retake_guard([7, 9, 7], clusters=[], valid_ids=[1])
    assert caught.value.unknown_ids == (7, 9)
    assert caught.value.to_dict()["unknown_ids"] == [7, 9]


def test_keep_best_uses_scores_when_present() -> None:
    result = apply_retake_guard(
        [4, 5],
        clusters=[RepetitionCluster((3, 4, 5))],
        valid_ids=[3, 4, 5],
        strategy="keep_best",
        scores={3: 0.9, 4: 0.4, 5: 0.2},
    )
    assert result.discard_sentence_ids == (4, 5)
    assert result.restored_sentence_ids == ()
    assert "keep_best" not in result.reasoning


def test_keep_best_without_scores_falls_back_to_last() -> None:
    result = apply_retake_guard(
        [4],
        clusters=[RepetitionCluster((3, 4))],
        valid_ids=[3, 4],
        strategy="keep_best",
        scores=None,
    )
    assert result.restored_sentence_ids == (4,)


def test_keep_best_ignores_a_cluster_without_scores_for_its_members() -> None:
    result = apply_retake_guard(
        [9],
        clusters=[RepetitionCluster((8, 9))],
        valid_ids=[8, 9],
        strategy="keep_best",
        scores={1: 1.0},
    )
    assert result.restored_sentence_ids == (9,)


def test_keep_last_ignores_scores() -> None:
    result = apply_retake_guard(
        [4],
        clusters=[RepetitionCluster((3, 4))],
        valid_ids=[3, 4],
        strategy="keep_last",
        scores={3: 0.99, 4: 0.01},
    )
    assert result.restored_sentence_ids == (4,)


def test_exact_repetition_grouping_skips_blank_and_single_sentences() -> None:
    clusters = cluster_exact_repetitions(
        [
            (1, ""),
            (2, "Hello there."),
            (3, "  hello   there "),
            (4, "A different line."),
            (5, "A different line!"),
            (6, "Tail."),
        ]
    )
    assert [cluster.sentence_ids for cluster in clusters] == [(2, 3), (4, 5)]


def test_normalization_is_case_and_punctuation_insensitive() -> None:
    assert normalize_sentence_text("  Hello, WORLD!  ") == "hello, world"


def test_no_clusters_for_an_empty_transcript() -> None:
    assert cluster_exact_repetitions([]) == ()


def test_guard_with_no_clusters_is_a_pass_through() -> None:
    result = apply_retake_guard([1], clusters=[], valid_ids=[1])
    assert result.discard_sentence_ids == (1,)


def test_guard_accepts_a_plain_string_strategy_value() -> None:
    result = apply_retake_guard(
        [2],
        clusters=[RepetitionCluster((1, 2))],
        valid_ids=[1, 2],
        strategy=cast(str, "keep_last"),
    )
    assert result.restored_sentence_ids == (2,)
