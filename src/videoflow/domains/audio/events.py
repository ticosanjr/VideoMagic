"""Small, dependency-free audio-event classifier."""

# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.application.non_speech import (
    _flatness,
    _harmonicity,
    candidate_bursts,
    detect_impulsive_noise,
)

from .events_ast import *  # noqa: F401,F403
from .events_model import *  # noqa: F401,F403


def detect_audio_events(
    pcm: np.ndarray,
    word_spans: Sequence[tuple[int, int]],
    *,
    sample_rate: int = 48_000,
    model: EventModel | None = None,
    frame_ms: int = 10,
    min_ms: int = 40,
    max_ms: int = 600,
    margin_ms: int = 80,
    rms_threshold: float = 0.02,
    use_ast: bool = False,
    ast_threshold: float = 0.1,
) -> list[tuple[int, int]]:
    """Detect non-speech events with AST, the trained model, or the heuristic."""

    heuristic = detect_impulsive_noise(
        pcm,
        word_spans,
        sample_rate=sample_rate,
        frame_ms=frame_ms,
        min_ms=min_ms,
        max_ms=max_ms,
        margin_ms=margin_ms,
        rms_threshold=rms_threshold,
    )
    if use_ast:
        candidates = candidate_bursts(
            pcm,
            word_spans,
            sample_rate=sample_rate,
            frame_ms=frame_ms,
            min_ms=min_ms,
            max_ms=max_ms,
            margin_ms=margin_ms,
            rms_threshold=rms_threshold,
        )
        ast = score_ast_candidates(
            pcm,
            candidates,
            sample_rate=sample_rate,
            threshold=ast_threshold,
        )
        if ast:
            heuristic = sorted({*heuristic, *ast})
    if model is None:
        return heuristic
    candidates = candidate_bursts(
        pcm,
        word_spans,
        sample_rate=sample_rate,
        frame_ms=frame_ms,
        min_ms=min_ms,
        max_ms=max_ms,
        margin_ms=margin_ms,
        rms_threshold=rms_threshold,
    )
    scored = score_candidates(pcm, candidates, model, sample_rate=sample_rate)
    return sorted({*heuristic, *scored})
