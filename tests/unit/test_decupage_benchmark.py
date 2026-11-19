from __future__ import annotations

from scripts.decupage_benchmark import markdown, run_benchmark, self_test_manifest


def test_self_test_meets_deterministic_thresholds() -> None:
    payload = run_benchmark(self_test_manifest())
    assert payload["status"] == "synthetic"
    assert payload["physical_acceptance_pending"] is True
    assert payload["failures"] == []
    assert payload["metrics"]["retake_recall"] >= 0.95
    assert payload["metrics"]["noise_recall"] >= 0.92
    assert payload["metrics"]["false_positive_ratio"] <= 0.01
    assert payload["metrics"]["frame_quantized"] is True
    assert payload["plan"]["active_spans"]


def test_markdown_surfaces_pending_physical_metrics() -> None:
    text = markdown(run_benchmark(self_test_manifest()))
    assert "Physical acceptance pending" in text
    assert "clipped syllables" in text
    assert "audio clicks" in text
