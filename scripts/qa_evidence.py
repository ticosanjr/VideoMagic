#!/usr/bin/env python
"""Collect NLE and accessibility QA evidence without fabricating sign-off.

Usage:
    python scripts/qa_evidence.py --exports <dir> --job-output <dir>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from videoflow.application.nle_extras import nle_extras_from_output  # noqa: E402
from videoflow.application.nle_validation import validate_nle_exports  # noqa: E402


def _run(command: list[str], timeout: float = 180.0) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "command": command, "error": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _flatpak_kdenlive() -> dict[str, object]:
    if shutil.which("flatpak") is None:
        return {"found": False, "reason": "flatpak is not installed"}
    listed = _run(["flatpak", "list", "--app", "--columns=application,version"], 30)
    version = ""
    for line in str(listed.get("stdout") or "").splitlines():
        parts = line.split("\t")
        if parts and parts[0] == "org.kde.kdenlive":
            version = parts[1] if len(parts) > 1 else ""
    if not version:
        return {"found": False, "reason": "org.kde.kdenlive is not installed"}
    return {"found": True, "version": version}


def _melt_render(project: Path) -> dict[str, object]:
    flatpak = _flatpak_kdenlive()
    if not bool(flatpak.get("found")):
        return {"skipped": True, **flatpak}
    output = Path.home() / ".cache" / "videoflow" / "qa" / "kdenlive-melt.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    result = _run(
        [
            "flatpak",
            "run",
            "--command=melt",
            "org.kde.kdenlive",
            "-consumer",
            f"avformat:{output}",
            str(project),
        ],
        timeout=180,
    )
    result.update(
        {
            "output": str(output),
            "bytes": output.stat().st_size if output.is_file() else 0,
            "ok": bool(result.get("ok")) and output.is_file() and output.stat().st_size > 0,
        }
    )
    return result


def _accessibility_environment() -> dict[str, object]:
    orca = shutil.which("orca")
    version = _run([orca, "--version"], 10) if orca else {}
    display = os.environ.get("DISPLAY", "")
    snapshots = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "ui" / "e2e").glob("*-snapshots/*.png")
    )
    return {
        "os": sys.platform,
        "display": display,
        "display_available": bool(display),
        "orca": orca,
        "orca_version": str(version.get("stdout") or version.get("stderr") or "").strip()
        if orca
        else "",
        "visual_baselines": snapshots,
        "automated_commands": [
            "cd ui && npx playwright test e2e/a11y.spec.ts",
            "cd ui && npm test",
            "cd ui && npm run check",
        ],
    }


def _compare(report: dict, extras: object) -> list[str]:
    problems: list[str] = []
    for name, result in report.get("exports", {}).items():
        marker_count = result.get("guides") if name == "kdenlive" else result.get("markers")
        if getattr(extras, "markers", None) and not marker_count:
            problems.append(f"{name}: no native markers")
        if getattr(extras, "titles", None) and not result.get("titles"):
            problems.append(f"{name}: no native titles")
        if getattr(extras, "color_filters", None) and not result.get("color_filters"):
            problems.append(f"{name}: no native colour filter")
        if name == "fcpxml" and getattr(extras, "audio_stem", None) and not result.get(
            "audio_stems"
        ):
            problems.append("fcpxml: no audio master stem")
        if name == "fcpxml" and getattr(extras, "broll", None) and not result.get(
            "broll_clips"
        ):
            problems.append("fcpxml: no B-roll lane")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--job-output", type=Path, default=None)
    parser.add_argument(
        "--out-dir", type=Path, default=ROOT / "docs" / "qa-evidence"
    )
    args = parser.parse_args(argv)

    exports = args.exports.expanduser().resolve()
    report = validate_nle_exports(exports)
    problems: list[str] = []
    if args.job_output is not None:
        extras = nle_extras_from_output(args.job_output.expanduser().resolve())
        problems = _compare(report, extras)
    report["problems"] = problems
    report["ok"] = bool(report.get("ok")) and not problems

    kdenlive_path = exports / "timeline.kdenlive"
    nle = {
        "structural": report,
        "kdenlive": _flatpak_kdenlive(),
        "melt": _melt_render(kdenlive_path) if kdenlive_path.is_file() else {"skipped": True},
    }
    accessibility = _accessibility_environment()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "generated_at": stamp,
        "exports": str(exports),
        "job_output": str(args.job_output) if args.job_output else "",
        "nle": nle,
        "accessibility": accessibility,
        "signoff": {
            "nle_reviewer": "",
            "nle_date": "",
            "accessibility_reviewer": "",
            "accessibility_date": "",
            "status": "pending human review",
        },
    }
    output_dir = args.out_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"qa-{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    melt = nle["melt"]
    markdown = [
        f"# QA evidence {stamp}",
        "",
        f"- Exports: `{exports}`",
        f"- Structural validation: **{'ok' if report.get('ok') else 'failed'}**",
        f"- Problems: {', '.join(problems) if problems else 'none'}",
        f"- Kdenlive: {nle['kdenlive'].get('version') or 'not installed'}",
        f"- MLT render: {'ok' if melt.get('ok') else 'skipped/failed'} "
        f"({melt.get('bytes', 0)} bytes)",
        f"- Orca: {accessibility['orca'] or 'not installed'} "
        f"{accessibility['orca_version']}",
        f"- Display: `{accessibility['display'] or 'none'}`",
        "",
        "## Automated evidence",
        "",
        "```bash",
        *[f"# {item}" for item in accessibility["automated_commands"]],
        "```",
        "",
        "Visual baselines:",
        *[f"- `{item}`" for item in accessibility["visual_baselines"]],
        "",
        "## Human sign-off",
        "",
        "This report does not sign the gate. A human must still:",
        "",
        "1. Import `timeline.kdenlive` in Kdenlive and check sequence, tracks,",
        "   affine zoom, transition, titles, guides, B-roll, colour, audio, and a",
        "   short render.",
        "2. Run the accessibility checklist with Orca, keyboard, 200% zoom,",
        "   light/high-contrast themes, and reduced motion.",
        "",
        "| Gate | Reviewer | Date | Result |",
        "| --- | --- | --- | --- |",
        "| NLE |  |  | pending |",
        "| Accessibility |  |  | pending |",
        "",
    ]
    markdown_path = output_dir / f"qa-{stamp}.md"
    markdown_path.write_text("\n".join(markdown), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
            indent=2,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
