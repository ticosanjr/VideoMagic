"""Dynamic-time-warping alignment helpers."""

# ruff: noqa: F401
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.domain.errors import IngestError
from videoflow.runtime import find_binary

SAMPLE_RATE = 16_000
FRAME_LENGTH = 400  # 25 ms
FRAME_HOP = 160  # 10 ms
N_MELS = 64
FMIN = 80.0
FMAX = 7600.0
WINDOW_FRAMES = 100  # 1 s
WINDOW_HOP = 50  # 0.5 s
SEGMENTS = 8
EPSILON = 1e-10



def _cost_matrix(
    source: np.ndarray,
    target: np.ndarray,
    *,
    source_speech: np.ndarray | None = None,
    target_speech: np.ndarray | None = None,
    speech_penalty: float = 0.0,
) -> np.ndarray:
    similarity = np.clip(source @ target.T, -1.0, 1.0)
    cost = np.clip(1.0 - similarity, 0.0, 2.0).astype(np.float32)
    if (
        speech_penalty > 0
        and source_speech is not None
        and target_speech is not None
    ):
        cost += speech_penalty * np.abs(
            source_speech[:, None] - target_speech[None, :]
        )
    return cost


def _median_filter(values: np.ndarray, size: int = 5) -> np.ndarray:
    if size <= 1 or values.size < size:
        return values.copy()
    half = size // 2
    padded = np.pad(values, (half, half), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, size)
    return np.median(windows, axis=1)


def dtw_subsequence(
    source: np.ndarray,
    target: np.ndarray,
    *,
    source_speech: np.ndarray | None = None,
    target_speech: np.ndarray | None = None,
    speech_penalty: float = 0.25,
    gap_source: float = 2.0,
) -> tuple[list[tuple[int, int]], float]:
    """Align a short sequence to a subsequence of a longer one.

    Skipping target windows is free; skipping source windows is expensive.
    The result is a monotonic list of ``(source_index, target_index)`` matches.
    """

    source_data = np.asarray(source, dtype=np.float32)
    target_data = np.asarray(target, dtype=np.float32)
    if source_data.ndim != 2 or target_data.ndim != 2:
        raise ValueError("source and target must be 2-D matrices")
    if source_data.shape[0] == 0 or target_data.shape[0] == 0:
        return [], 0.0
    cost = _cost_matrix(
        source_data,
        target_data,
        source_speech=source_speech,
        target_speech=target_speech,
        speech_penalty=speech_penalty,
    )
    n, m = cost.shape
    peak = np.float32(1e9)
    dp = np.full((n, m), peak, dtype=np.float32)
    choice = np.zeros((n, m), dtype=np.uint8)
    dp[0] = np.minimum.accumulate(cost[0])
    for index in range(1, m):
        choice[0, index] = 0 if cost[0, index] <= dp[0, index - 1] else 1
    for row in range(1, n):
        previous = dp[row - 1]
        diagonal = np.full(m, peak, dtype=np.float32)
        diagonal[1:] = previous[:-1] + cost[row, 1:]
        upward = previous + np.float32(gap_source)
        base = np.minimum(diagonal, upward)
        current = np.minimum.accumulate(base)
        left = np.zeros(m, dtype=bool)
        left[1:] = current[:-1] < base[1:]
        choice[row] = np.where(
            left,
            1,
            np.where(diagonal <= upward, 0, 2),
        ).astype(np.uint8)
        dp[row] = current
    column = int(np.argmin(dp[-1]))
    total = float(dp[-1, column])
    row = n - 1
    matches: list[tuple[int, int]] = []
    while row >= 0 and column >= 0:
        direction = int(choice[row, column])
        if direction == 0:
            matches.append((row, column))
            row -= 1
            column -= 1
        elif direction == 1:
            column -= 1
        else:
            row -= 1
    matches.reverse()
    return matches, total


def dtw_symmetric(
    reference: np.ndarray,
    output: np.ndarray,
    *,
    reference_speech: np.ndarray | None = None,
    output_speech: np.ndarray | None = None,
    speech_penalty: float = 0.25,
    gap: float = 0.2,
    band: int | None = None,
) -> list[tuple[int, int]]:
    """Monotonic one-to-one alignment with gap penalties on both sides."""

    reference_data = np.asarray(reference, dtype=np.float32)
    output_data = np.asarray(output, dtype=np.float32)
    if reference_data.ndim != 2 or output_data.ndim != 2:
        raise ValueError("reference and output must be 2-D matrices")
    n, m = reference_data.shape[0], output_data.shape[0]
    if n == 0 or m == 0:
        return []
    cost = _cost_matrix(
        reference_data,
        output_data,
        source_speech=reference_speech,
        target_speech=output_speech,
        speech_penalty=speech_penalty,
    )
    peak = np.float32(1e9)
    dp = np.full((n, m), peak, dtype=np.float32)
    choice = np.zeros((n, m), dtype=np.uint8)
    dp[0, 0] = cost[0, 0]
    for column in range(1, m):
        dp[0, column] = dp[0, column - 1] + np.float32(gap)
        choice[0, column] = 1
    for row in range(1, n):
        dp[row, 0] = dp[row - 1, 0] + np.float32(gap)
        choice[row, 0] = 2
    for row in range(1, n):
        low = 1 if band is None else max(1, row - band)
        high = m - 1 if band is None else min(m - 1, row + band)
        if low > high:
            continue
        previous = dp[row - 1]
        columns = np.arange(low, high + 1)
        diagonal = previous[low - 1 : high] + cost[row, low : high + 1]
        upward = previous[low : high + 1] + np.float32(gap)
        base = np.minimum(diagonal, upward)
        row_values = np.minimum.accumulate(
            base - columns.astype(np.float32) * np.float32(gap)
        ) + columns.astype(np.float32) * np.float32(gap)
        left = np.zeros(row_values.size, dtype=bool)
        if row_values.size > 1:
            left[1:] = row_values[:-1] < base[1:]
        dp[row, low : high + 1] = row_values
        choice[row, low : high + 1] = np.where(
            left,
            1,
            np.where(diagonal <= upward, 0, 2),
        ).astype(np.uint8)
    row, column = n - 1, m - 1
    matches: list[tuple[int, int]] = []
    while row >= 0 and column >= 0:
        direction = int(choice[row, column])
        if direction == 0:
            matches.append((row, column))
            row -= 1
            column -= 1
        elif direction == 1:
            column -= 1
        else:
            row -= 1
    matches.reverse()
    return matches
