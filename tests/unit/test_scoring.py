"""Scoring profiles and ranking rules."""

from __future__ import annotations

from dataclasses import dataclass

from videoflow.application.scoring import (
    PROFILES,
    profile_weights,
    rerank,
    similar,
)


@dataclass
class Clip:
    title: str
    score: float = 0.0
    virality_score: float = 0.0
    score_breakdown: tuple[tuple[str, float], ...] = ()


def test_every_documented_profile_exists() -> None:
    for name in ("default", "hook", "education", "podcast", "tiktok", "youtube"):
        assert name in PROFILES
    assert PROFILES["default"] == {}


def test_analytics_weights_override_the_profile() -> None:
    weights = profile_weights("hook", {"markers": 4.0, "custom": 2.0})
    assert weights["markers"] == 4.0
    assert weights["custom"] == 2.0


def test_rerank_applies_weights_and_sorts() -> None:
    clips = [
        Clip("low", score_breakdown=(("markers", 1.0), ("duration", 5.0))),
        Clip("high", score_breakdown=(("markers", 5.0), ("duration", 1.0))),
    ]

    ranked = rerank(clips, {"markers": 2.0})

    assert [clip.title for clip in ranked] == ["high", "low"]
    assert ranked[0].score == 11.0
    assert ranked[0].virality_score == 44.0


def test_rerank_drops_near_duplicate_titles() -> None:
    clips = [
        Clip("segredo da produtividade real", score_breakdown=(("markers", 5.0),)),
        Clip("segredo da produtividade real", score_breakdown=(("markers", 4.0),)),
        Clip("outro assunto completamente diferente", score_breakdown=(("markers", 3.0),)),
    ]

    ranked = rerank(clips, {})

    assert len(ranked) == 2
    assert ranked[0].virality_score == 20.0


def test_rerank_respects_top_k() -> None:
    titles = ["alpha beta", "gamma delta", "epsilon zeta", "eta theta"]
    clips = [
        Clip(title, score_breakdown=(("markers", index),))
        for index, title in enumerate(titles, start=1)
    ]

    assert len(rerank(clips, {}, top_k=2)) == 2


def test_similarity_needs_shared_content_words() -> None:
    assert similar("segredo produtividade", "segredo produtividade") == 1.0
    assert similar("segredo", "segredo") == 0.0
    assert similar("a b c d", "w x y z") == 0.0
