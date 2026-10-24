"""Golden-set calibration for Short selection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.scoring import evaluate_cases

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "shorts.json"


def cases() -> list[dict[str, object]]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


def test_calibrated_profiles_beat_the_default_baseline() -> None:
    baseline = evaluate_cases(cases(), top_k=1, use_case_profiles=False)
    calibrated = evaluate_cases(cases(), top_k=1, use_case_profiles=True)

    assert calibrated["precision_at_k"] > baseline["precision_at_k"]
    assert calibrated["precision_at_k"] >= 0.9
    assert calibrated["recall"] >= baseline["recall"]
    assert calibrated["duplicates"] == 0
    assert calibrated["coverage"] >= 0.9
    assert calibrated["approval_rate"] >= 0.9
    assert calibrated["latency_ms"] >= 0
    assert calibrated["cost_usd"] == 0.0


def test_every_case_produces_a_selection() -> None:
    report = evaluate_cases(cases(), top_k=2, use_case_profiles=True)

    assert report["cases"] == len(cases())
    assert all(entry["selected"] for entry in report["per_case"])


def test_top_k_limits_the_selection() -> None:
    report = evaluate_cases(cases(), top_k=1, use_case_profiles=True)
    assert all(len(entry["selected"]) <= 1 for entry in report["per_case"])

    wider = evaluate_cases(cases(), top_k=2, use_case_profiles=True)
    assert sum(len(entry["selected"]) for entry in wider["per_case"]) >= sum(
        len(entry["selected"]) for entry in report["per_case"]
    )


@pytest.mark.parametrize(
    "profile", ["default", "hook", "education", "podcast", "tiktok", "youtube"]
)
def test_profiles_are_usable_for_every_case(profile: str) -> None:
    report = evaluate_cases(
        cases(), top_k=1, use_case_profiles=False, default_profile=profile
    )
    assert report["cases"] == len(cases())
    assert 0.0 <= report["precision_at_k"] <= 1.0
