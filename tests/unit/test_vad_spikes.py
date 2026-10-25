from __future__ import annotations

from videoflow.application.vad import postprocess_spans
from videoflow.steps.audio import VadParams


def test_spike_suppression_and_gap_merge() -> None:
    rate = 48000
    spans = [
        (0, 4800),          # 100 ms
        (5000, 6000),       # 20 ms spike
        (7000, 17000),      # 208 ms
        (18000, 28000),     # 208 ms, 20 ms gap from previous
    ]
    cleaned = postprocess_spans(
        spans,
        rate,
        spike_suppression_ms=50,
        merge_gap_ms=30,
    )
    assert cleaned == [(0, 4800), (7000, 28000)]


def test_vad_params_expose_recut_controls() -> None:
    params = VadParams.model_validate(
        {
            "noise_db": -34,
            "speech_threshold": 0.62,
            "min_silence_ms": 280,
            "min_speech_ms": 140,
            "pad_before_ms": 70,
            "pad_after_ms": 110,
            "spike_suppression_ms": 160,
            "merge_gap_ms": 90,
        }
    )
    assert params.spike_suppression_ms == 160
    assert params.merge_gap_ms == 90
