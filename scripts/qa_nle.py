#!/usr/bin/env python
"""QA for NLE exports: structure, finishing elements, and join transitions.

Usage:
    python scripts/qa_nle.py <exports-dir> [--job-output <job-dir>] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from videoflow.application.nle_extras import nle_extras_from_output  # noqa: E402
from videoflow.application.nle_validation import validate_nle_exports  # noqa: E402


def compare(report: dict, extras) -> list[str]:
    """Add errors when native finishing elements are missing."""

    problems: list[str] = []
    for name, result in report.get("exports", {}).items():
        marker_count = result.get("guides") if name == "kdenlive" else result.get("markers")
        if extras.markers and not marker_count:
            problems.append(f"{name}: no native markers")
        if extras.titles and not result.get("titles"):
            problems.append(f"{name}: no native titles")
        if extras.color_filters and not result.get("color_filters"):
            problems.append(f"{name}: no native colour filter")
        if name == "fcpxml" and extras.audio_stem and not result.get("audio_stems"):
            problems.append("fcpxml: no audio master stem")
        if name == "fcpxml" and extras.broll and not result.get("broll_clips"):
            problems.append("fcpxml: no B-roll lane")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--job-output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = validate_nle_exports(args.directory)
    problems: list[str] = []
    if args.job_output is not None:
        extras = nle_extras_from_output(args.job_output)
        report["expected"] = {
            "markers": len(extras.markers),
            "titles": len(extras.titles),
            "broll": len(extras.broll),
            "color_filters": len(extras.color_filters),
            "audio_stem": bool(extras.audio_stem),
        }
        problems = compare(report, extras)
    report["problems"] = problems
    report["ok"] = bool(report.get("ok")) and not problems
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for name, result in report.get("exports", {}).items():
            state = "ok" if result["ok"] else "fail"
            print(f"{name:10} {state:4} clips={result.get('clips')} "
                  f"transitions={result.get('transitions')} "
                  f"titles={result.get('titles')} markers={result.get('markers')}")
        for item in report.get("exports", {}).get("fcpxml", {}).get("warnings", []):
            print(f"warning: {item}")
        for item in problems:
            print(f"problem: {item}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
