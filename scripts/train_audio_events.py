#!/usr/bin/env python
"""Train the audio-event classifier from human-edit weak labels.

A candidate burst outside every word is a positive (cough/throat clear) when the
human edit removed a short internal region around it and kept speech on both
sides. A burst inside a kept region is a negative. Candidates inside a large
removed take are ignored because the cut was editorial, not acoustic.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np

from videoflow.application.audio_events import (
    FEATURE_NAMES,
    save_model,
    span_features,
    train_model,
)
from videoflow.application.non_speech import candidate_bursts, load_pcm_mono
from videoflow.application.reference_edl import load_reference_edl
from videoflow.domain.state import ProjectState


def _inside(moment: float, intervals: list[tuple[float, float]]) -> bool:
    return any(start <= moment <= end for start, end in intervals)


def _flanked(
    start: float,
    end: float,
    intervals: list[tuple[float, float]],
    *,
    window: float = 1.5,
) -> bool:
    before = any(
        interval_end <= start + 0.05 and interval_end >= start - window
        for _start, interval_end in intervals
    )
    after = any(
        interval_start >= end - 0.05 and interval_start <= end + window
        for interval_start, _end in intervals
    )
    return before and after


def _case(
    project: Path,
    edl_path: Path,
) -> tuple[list[np.ndarray], list[int], dict[str, int]]:
    state = ProjectState.model_validate(
        json.loads((project / "project_state.json").read_text(encoding="utf-8"))
    )
    edl = load_reference_edl(edl_path)
    pcm = load_pcm_mono(project / "work" / "source.wav", sample_rate=48_000)
    words = [
        (word.start_sample, word.end_sample)
        for sentence in state.transcript
        for word in sentence.words
    ]
    candidates = candidate_bursts(
        pcm,
        words,
        sample_rate=48_000,
        min_ms=40,
        max_ms=900,
        margin_ms=80,
    )
    features: list[np.ndarray] = []
    labels: list[int] = []
    stats = {"candidates": len(candidates), "positive": 0, "negative": 0, "ignored": 0}
    for start, end in candidates:
        midpoint = (start + end) / 2 / 48_000
        kept = _inside(midpoint, edl.kept_intervals)
        if kept:
            label = 0
        elif _flanked(start / 48_000, end / 48_000, edl.kept_intervals):
            label = 1
        else:
            stats["ignored"] += 1
            continue
        vector = span_features(pcm, start, end, sample_rate=48_000)
        if vector is None:
            stats["ignored"] += 1
            continue
        features.append(vector)
        labels.append(label)
        stats["positive" if label else "negative"] += 1
    return features, labels, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        nargs=2,
        action="append",
        metavar=("PROJECT", "EDL"),
        required=True,
        help="project directory with project_state.json/work/source.wav and its EDL",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    features: list[np.ndarray] = []
    labels: list[int] = []
    for project, edl in args.case:
        case_features, case_labels, stats = _case(Path(project), Path(edl))
        features.extend(case_features)
        labels.extend(case_labels)
        print(
            f"{Path(project).name}: candidates={stats['candidates']} "
            f"positive={stats['positive']} negative={stats['negative']} "
            f"ignored={stats['ignored']}"
        )
    if len(features) < 8:
        print("not enough labelled events")
        return 1
    matrix = np.asarray(features, dtype=np.float64)
    targets = np.asarray(labels, dtype=np.float64)
    order = list(range(len(features)))
    random.Random(7).shuffle(order)
    split = max(4, int(len(order) * 0.8))
    train_index = order[:split]
    test_index = order[split:]
    model = train_model(
        matrix[train_index],
        targets[train_index],
        threshold=args.threshold,
    )
    print(
        "train:",
        f"n={len(train_index)}",
        f"accuracy={model.metrics['accuracy'] if model.metrics else 0}",
        f"precision={model.metrics['precision'] if model.metrics else 0}",
        f"recall={model.metrics['recall'] if model.metrics else 0}",
    )
    if test_index:
        scores = np.asarray(
            [
                model.score(matrix[index])
                for index in test_index
            ]
        )
        predicted = (scores >= model.threshold).astype(int)
        expected = targets[test_index].astype(int)
        true_positive = int(np.sum((predicted == 1) & (expected == 1)))
        false_positive = int(np.sum((predicted == 1) & (expected == 0)))
        false_negative = int(np.sum((predicted == 0) & (expected == 1)))
        precision = true_positive / max(1, true_positive + false_positive)
        recall = true_positive / max(1, true_positive + false_negative)
        print(
            "test:",
            f"n={len(test_index)}",
            f"accuracy={float(np.mean(predicted == expected)):.4f}",
            f"precision={precision:.4f}",
            f"recall={recall:.4f}",
        )
    path = save_model(model, args.out)
    print("written:", path)
    print("features:", ", ".join(FEATURE_NAMES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
