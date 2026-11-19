"""Deterministic ASS caption effect and width QA."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _ass_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, centis = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(centis) / 100


def audit_ass(path: Path, *, effect: str = "static", max_chars: int = 0) -> dict[str, Any]:
    source = Path(path).expanduser()
    issues: list[dict[str, Any]] = []
    if not source.is_file():
        return {
            "ok": False,
            "issues": [{"kind": "missing_ass", "message": f"ASS file not found: {source}"}],
        }
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    spans: list[tuple[float, float]] = []
    for line in lines:
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        start = _ass_seconds(parts[1])
        end = _ass_seconds(parts[2])
        text = parts[9]
        spans.append((start, end))
        if effect != "static":
            tags = re.findall(r"\{[^}]*\\kf?(\d+)[^}]*\}", text)
            if not tags:
                issues.append(
                    {
                        "kind": "caption_effect",
                        "message": "karaoke effect requested but line has no \\k/\\kf tags",
                        "start_sec": round(start, 3),
                    }
                )
            else:
                total = sum(int(item) for item in tags) / 100.0
                if total <= 0 or abs(total - (end - start)) > 0.06:
                    issues.append(
                        {
                            "kind": "caption_timing",
                            "message": (
                                f"karaoke duration {total:.2f}s does not match "
                                f"line duration {end - start:.2f}s"
                            ),
                            "start_sec": round(start, 3),
                        }
                    )
                if any(int(item) <= 0 for item in tags):
                    issues.append(
                        {
                            "kind": "caption_zero_duration",
                            "message": "caption contains a zero-duration word",
                            "start_sec": round(start, 3),
                        }
                    )
        if "\\\\c&H" in text or "\\\\k" in text or "\\\\kf" in text:
            issues.append(
                {
                    "kind": "caption_escape",
                    "message": "caption contains a double-escaped ASS tag",
                    "start_sec": round(start, 3),
                }
            )
        plain = re.sub(r"\{[^}]*\}", "", text).replace("\\N", " ").strip()
        if re.search(r"(?<!\\)\\[cCkK]", plain):
            issues.append(
                {
                    "kind": "caption_escape",
                    "message": "caption contains an ASS tag outside an override block",
                    "start_sec": round(start, 3),
                }
            )
        if max_chars > 0 and len(plain) > max_chars:
            issues.append(
                {
                    "kind": "caption_width",
                    "message": f"caption line has {len(plain)} chars (max {max_chars})",
                    "start_sec": round(start, 3),
                }
            )
    spans.sort()
    for previous, current in zip(spans, spans[1:], strict=False):
        if current[0] < previous[1] - 0.001:
            issues.append(
                {
                    "kind": "caption_overlap",
                    "message": (
                        f"caption starts at {current[0]:.2f}s before the previous "
                        f"line ends at {previous[1]:.2f}s"
                    ),
                    "start_sec": round(current[0], 3),
                }
            )
    return {"ok": not issues, "issues": issues, "path": str(source)}


__all__ = ["audit_ass"]
