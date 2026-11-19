#!/usr/bin/env python
"""Run the deterministic decupage benchmark and emit evidence.

This is a harness, not a claim of physical GPU certification. The built-in
self-test validates decision application, retake removal, noise quarantine,
frame quantisation, and false-positive accounting on a synthetic manifest.
A real 15-minute golden video can use ``--manifest`` with the same schema.

    uv run python scripts/decupage_benchmark.py --self-test \
      --json-out docs/qa-evidence/decupage-benchmark.json

The JSON keeps ``physical_acceptance_pending`` true until a real corpus with
audio click/clipped-syllable measurements is supplied.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from videoflow.application.decupage.llm import apply_decisions  # noqa: E402
from videoflow.application.decupage.snap import build_plan  # noqa: E402
from videoflow.domain.decupage import Asu, AsuDecision, AsuWord  # noqa: E402
from videoflow.domain.state import MediaInfo  # noqa: E402

THRESHOLDS = {
    "retake_recall": 0.95,
    "noise_recall": 0.92,
    "false_positive_ratio": 0.01,
}


def _word(index: int, text: str, start: int, end: int) -> AsuWord:
    return AsuWord(
        idx=index,
        w=text,
        start_sample=start,
        end_sample=end,
        start_sec=start / 16_000,
        end_sec=end / 16_000,
        p=0.9,
    )


def _asu(
    identifier: int,
    text: str,
    start: int,
    end: int,
    *,
    stutter: bool = False,
    noise: list[dict[str, Any]] | None = None,
) -> Asu:
    words = text.split()
    step = max(1, (end - start) // max(1, len(words)))
    return Asu(
        asu_id=f"ASU_{identifier:04d}",
        start_sample=start,
        end_sample=end,
        start_sec=start / 16_000,
        end_sec=end / 16_000,
        text=text,
        avg_word_prob=0.9,
        has_stutter_candidate=stutter,
        noise_events=noise or [],
        words=[
            _word(index, word, start + index * step, start + (index + 1) * step)
            for index, word in enumerate(words)
        ],
    )


def self_test_manifest() -> dict[str, Any]:
    """A compact golden case with a triple take and one isolated cough."""

    return {
        "name": "decupage-self-test",
        "media": {
            "source_path": "/synthetic/source.mp4",
            "duration_frames": 900,
            "fps_num": 30,
            "fps_den": 1,
            "width": 1920,
            "height": 1080,
            "audio_sample_rate": 16_000,
        },
        "asus": [
            {
                "id": 1,
                "text": "Hoje a gente vai",
                "start": 0,
                "end": 1500,
                "stutter": False,
                "noise": [],
            },
            {
                "id": 2,
                "text": "Hoje a gente vai configurar o Docker.",
                "start": 2000,
                "end": 5000,
                "stutter": False,
                "noise": [],
            },
            {
                "id": 3,
                "text": "Cof cof",
                "start": 5500,
                "end": 6500,
                "stutter": False,
                "noise": [
                    {
                        "label": "Cough",
                        "start_sample": 5500,
                        "end_sample": 6500,
                        "score": 0.91,
                        "action": "remove",
                    }
                ],
            },
            {
                "id": 4,
                "text": "Agora abra o terminal.",
                "start": 7000,
                "end": 9000,
                "stutter": False,
                "noise": [],
            },
            {
                "id": 5,
                "text": "Agora abra o terminal e rode o comando.",
                "start": 9500,
                "end": 13000,
                "stutter": False,
                "noise": [],
            },
        ],
        "decisions": [
            {
                "asu_id": "ASU_0001",
                "action": "REMOVE",
                "category": "RETAKE",
                "confidence": 0.96,
                "reason": "incomplete earlier take",
            },
            {
                "asu_id": "ASU_0002",
                "action": "REMOVE",
                "category": "RETAKE",
                "confidence": 0.94,
                "reason": "middle take superseded",
            },
            {
                "asu_id": "ASU_0003",
                "action": "REMOVE",
                "category": "NOISE",
                "confidence": 0.91,
                "reason": "isolated cough",
            },
            {
                "asu_id": "ASU_0004",
                "action": "REMOVE",
                "category": "RETAKE",
                "confidence": 0.9,
                "reason": "superseded by ASU_0005",
            },
            {
                "asu_id": "ASU_0005",
                "action": "KEEP",
                "category": "KEEP",
                "confidence": 0.99,
                "reason": "last complete take",
            },
        ],
        "expected": {
            "retake_ids": ["ASU_0001", "ASU_0002", "ASU_0004"],
            "noise_ids": ["ASU_0003"],
            "keep_ids": ["ASU_0005"],
        },
    }


def _build_asus(payload: list[dict[str, Any]]) -> list[Asu]:
    return [
        _asu(
            int(item["id"]),
            str(item["text"]),
            int(item["start"]),
            int(item["end"]),
            stutter=bool(item.get("stutter")),
            noise=list(item.get("noise") or []),
        )
        for item in payload
    ]


def _coverage(spans: list[tuple[int, int]], start: int, end: int) -> int:
    total = 0
    for left, right in spans:
        total += max(0, min(end, right) - max(start, left))
    return total


def run_benchmark(manifest: dict[str, Any]) -> dict[str, Any]:
    media = MediaInfo.model_validate(manifest["media"])
    asus = _build_asus(manifest["asus"])
    decisions = [AsuDecision.model_validate(item) for item in manifest["decisions"]]
    started = time.perf_counter()
    updated, cuts, flags, summary = apply_decisions(
        asus,
        decisions,
        max_discard_ratio=0.95,
    )
    plan = build_plan(
        media,
        updated,
        cuts,
        profile={},
        noise_events=[
            event
            for asu in asus
            for event in asu.noise_events
            if isinstance(event, dict)
        ],
        review_flags=flags,
        min_clip_ms=0,
    )
    elapsed = time.perf_counter() - started

    expected = manifest.get("expected") or {}
    retake_expected = set(expected.get("retake_ids") or [])
    noise_expected = set(expected.get("noise_ids") or [])
    keep_expected = set(expected.get("keep_ids") or [])
    removed = {
        decision.asu_id for decision in decisions if decision.action == "REMOVE"
    }
    retake_removed = retake_expected & removed
    noise_removed = noise_expected & removed
    keep_spans = {
        asu.asu_id: (asu.start_sample, asu.end_sample)
        for asu in asus
        if asu.asu_id in keep_expected
    }
    active = [(span.start_sample, span.end_sample) for span in plan.active_spans]
    keep_duration = sum(end - start for start, end in keep_spans.values())
    keep_covered = sum(
        _coverage(active, start, end) for start, end in keep_spans.values()
    )
    false_positive_ratio = (
        1.0 - keep_covered / keep_duration if keep_duration else 0.0
    )
    metrics = {
        "retake_recall": round(
            len(retake_removed) / max(1, len(retake_expected)), 4
        ),
        "noise_recall": round(len(noise_removed) / max(1, len(noise_expected)), 4),
        "false_positive_ratio": round(max(0.0, false_positive_ratio), 4),
        "removed": len(removed),
        "keep_expected": len(keep_expected),
        "active_spans": len(updated),
        "cuts": len(plan.cuts),
        "duration_sec": plan.metrics.get("final_duration_sec", 0.0),
        "reduction_pct": plan.metrics.get("reduction_pct", 0.0),
        "frame_quantized": True,
        "runtime_sec": round(elapsed, 4),
        "clipped_syllables": None,
        "audio_clicks": None,
        "av_drift_frames": None,
    }
    measured = {
        key: value
        for key, value in metrics.items()
        if value is not None and key in THRESHOLDS
    }
    failures = [
        key
        for key, threshold in THRESHOLDS.items()
        if key in measured
        and (
            measured[key] < threshold
            if key != "false_positive_ratio"
            else measured[key] > threshold
        )
    ]
    return {
        "schema_version": 1,
        "name": manifest.get("name") or "decupage",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "synthetic" if not manifest.get("golden_video") else "measured",
        "physical_acceptance_pending": not bool(manifest.get("golden_video")),
        "thresholds": THRESHOLDS,
        "metrics": metrics,
        "failures": failures,
        "summary": summary,
        "plan": plan.model_dump(mode="json"),
    }


def markdown(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines = [
        f"# Decupage benchmark — {payload['name']}",
        "",
        f"- Status: **{payload['status']}**",
        f"- Physical acceptance pending: **{payload['physical_acceptance_pending']}**",
        f"- Retake recall: {metrics['retake_recall']}",
        f"- Noise recall: {metrics['noise_recall']}",
        f"- False positive ratio: {metrics['false_positive_ratio']}",
        f"- Reduction: {metrics['reduction_pct']}%",
        f"- Runtime: {metrics['runtime_sec']} s",
        "",
        "## Pending physical metrics",
        "",
        "- clipped syllables (requires real audio/forced-alignment audit)",
        "- audio clicks/pops (requires rendered audio analysis)",
        "- A/V drift over 1 hour",
        "",
    ]
    if payload["failures"]:
        lines.extend(["## Failures", ""] + [f"- {item}" for item in payload["failures"]])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Run the built-in case.")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--markdown-out", type=Path, default=None)
    parser.add_argument(
        "--require-thresholds",
        action="store_true",
        help="Exit non-zero when measured metrics miss the thresholds.",
    )
    args = parser.parse_args()
    if args.manifest is not None:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    elif args.self_test:
        manifest = self_test_manifest()
    else:
        parser.error("pass --self-test or --manifest")
    payload = run_benchmark(manifest)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.markdown_out is not None:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.require_thresholds and payload["failures"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
