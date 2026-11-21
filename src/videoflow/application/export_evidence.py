"""Preserve evidence when an export gate fails.

A failed export must leave enough material to diagnose the 2:1 bug without
re-running the whole pipeline: the error, the command, the intermediate
segments, and an ffprobe dump of every surviving file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoflow.runtime import find_binary


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _probe(path: Path) -> dict[str, Any]:
    ffprobe = find_binary("ffprobe")
    if ffprobe is None:
        return {"ok": False, "error": "ffprobe not found"}
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        return {"ok": False, "error": completed.stderr.strip()[-400:]}
    try:
        payload = json.loads(completed.stdout or "{}")
    except ValueError:
        return {"ok": False, "error": "invalid ffprobe JSON"}
    fmt = payload.get("format") or {}
    streams = [
        {
            "codec_type": item.get("codec_type"),
            "codec_name": item.get("codec_name"),
            "sample_rate": item.get("sample_rate"),
            "channels": item.get("channels"),
            "width": item.get("width"),
            "height": item.get("height"),
            "duration": item.get("duration"),
        }
        for item in payload.get("streams") or []
        if isinstance(item, dict)
    ]
    return {"ok": True, "format": fmt, "streams": streams}


def preserve_failed_export(
    output: Path | str,
    *,
    error: str,
    command: str = "",
    paths: tuple[Path, ...] = (),
) -> Path:
    """Copy intermediate artifacts into ``exports/_failed/<timestamp>``."""

    root = Path(output).expanduser()
    target = root / "exports" / "_failed" / _timestamp()
    target.mkdir(parents=True, exist_ok=True)
    (target / "failure.json").write_text(
        json.dumps(
            {
                "error": error,
                "command": command,
                "created_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    candidates: list[Path] = [root / "render" / "segments", root / "audio", *paths]
    probes: dict[str, Any] = {}
    for source in candidates:
        if not source.exists():
            continue
        if source.is_dir():
            destination = target / source.name
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns("*.tmp"))
            for item in sorted(destination.rglob("*")):
                if item.is_file():
                    probes[str(item.relative_to(target))] = _probe(item)
        elif source.is_file():
            destination = target / source.name
            shutil.copy2(source, destination)
            probes[destination.name] = _probe(destination)
    (target / "ffprobe.json").write_text(
        json.dumps(probes, indent=2) + "\n", encoding="utf-8"
    )
    return target


__all__ = ["preserve_failed_export"]
