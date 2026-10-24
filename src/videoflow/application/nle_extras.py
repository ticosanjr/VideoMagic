"""Build native NLE finishing inputs from one job output directory."""

from __future__ import annotations

import json
import re
from pathlib import Path

from videoflow.application.timeline_meta import load_meta
from videoflow.exporters.extras import NleBroll, NleExtras, NleMarker, NleTitle

ASS_TIME = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{2})$")


def _seconds(value: str) -> float:
    match = ASS_TIME.match(value.strip())
    if match is None:
        return 0.0
    hours, minutes, seconds, centis = (int(item) for item in match.groups())
    return hours * 3600 + minutes * 60 + seconds + centis / 100


def _titles(path: Path) -> tuple[NleTitle, ...]:
    if not path.is_file():
        return ()
    titles: list[NleTitle] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        text = re.sub(r"\{[^}]*\}", "", parts[9]).strip()
        if not text:
            continue
        titles.append(
            NleTitle(
                text=text,
                start_sec=_seconds(parts[1]),
                end_sec=_seconds(parts[2]),
                kind="title",
            )
        )
    return tuple(titles)


def _filters(path: Path) -> tuple[str, ...]:
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(str(item) for item in payload.get("filters", []) if str(item))


def _broll(output: Path) -> tuple[NleBroll, ...]:
    for name in ("broll-matches.json", "broll.json"):
        path = output / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        plan = payload.get("shorts", payload) if isinstance(payload, dict) else {}
        entries: list[NleBroll] = []
        for cues in plan.values() if isinstance(plan, dict) else []:
            for cue in cues if isinstance(cues, list) else []:
                if not isinstance(cue, dict) or not cue.get("path"):
                    continue
                entries.append(
                    NleBroll(
                        path=str(cue["path"]),
                        start_sec=float(cue.get("start_sec") or 0.0),
                        duration_sec=float(cue.get("duration_sec") or 2.0),
                        name=Path(str(cue["path"])).stem,
                    )
                )
        if entries:
            return tuple(entries)
    return ()


def nle_extras_from_output(output: Path) -> NleExtras:
    """Read markers, titles, B-roll, colour, and the audio master if present."""

    directory = Path(output)
    meta = load_meta(directory)
    markers = tuple(
        NleMarker(
            name=item.label or item.id,
            start_sec=item.time_sec,
            note=item.color,
            color=item.color,
        )
        for item in meta.markers
    )
    stems = directory / "audio" / "master.wav"
    colors = _filters(directory / "color" / "filters.json")
    audio = _filters(directory / "audio" / "master-filters.json")
    return NleExtras(
        markers=markers,
        titles=_titles(directory / "titles.ass"),
        broll=_broll(directory),
        color_filters=colors,
        audio_filters=audio,
        audio_stem=str(stems) if stems.is_file() else "",
    )
