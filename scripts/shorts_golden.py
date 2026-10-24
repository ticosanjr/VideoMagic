#!/usr/bin/env python
"""Print the golden-set report for Short selection profiles.

Usage:
    uv run python scripts/shorts_golden.py [--top-k 1] [--json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from videoflow.application.scoring import evaluate_cases

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "shorts.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--golden", type=Path, default=GOLDEN)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cases = json.loads(args.golden.read_text(encoding="utf-8"))["cases"]
    baseline = evaluate_cases(cases, top_k=args.top_k, use_case_profiles=False)
    calibrated = evaluate_cases(cases, top_k=args.top_k, use_case_profiles=True)
    report = {"baseline": baseline, "calibrated": calibrated}
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    def line(name: str, payload: dict[str, object]) -> str:
        return (
            f"{name:12} precision@{args.top_k}={payload['precision_at_k']:.2f} "
            f"recall={payload['recall']:.2f} coverage={payload['coverage']:.2f} "
            f"duplicates={payload['duplicates']} latency={payload['latency_ms']}ms "
            f"cost=${payload['cost_usd']:.2f}"
        )

    print(line("baseline", baseline))
    print(line("calibrated", calibrated))
    print()
    for case, base, cal in zip(
        cases, baseline["per_case"], calibrated["per_case"], strict=True
    ):
        print(
            f"{case['id']:28} {base['profile']:9} "
            f"{base['precision']:.2f} -> {cal['precision']:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
