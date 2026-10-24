"""Native NLE finishing inputs: markers, titles, B-roll, colour, and audio."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class NleMarker:
    name: str
    start_sec: float
    end_sec: float = 0.0
    note: str = ""
    color: str = ""


@dataclass(frozen=True, slots=True)
class NleTitle:
    text: str
    start_sec: float
    end_sec: float
    kind: str = "title"


@dataclass(frozen=True, slots=True)
class NleBroll:
    path: str
    start_sec: float
    duration_sec: float
    name: str = ""
    kind: str = "video"


@dataclass(frozen=True, slots=True)
class NleExtras:
    markers: tuple[NleMarker, ...] = ()
    titles: tuple[NleTitle, ...] = ()
    broll: tuple[NleBroll, ...] = ()
    color_filters: tuple[str, ...] = ()
    audio_filters: tuple[str, ...] = ()
    audio_stem: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


EMPTY = NleExtras()
