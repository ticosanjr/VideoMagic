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
    anchor: str = ""
    margin_x: int = 0
    margin_y: int = 0
    width_ratio: float = 1.0
    opacity: float = 1.0
    z: int = 10


@dataclass(frozen=True, slots=True)
class NleAdjustment:
    name: str
    start_sec: float
    end_sec: float
    lut_path: str = ""
    grain_amount: float = 0.0
    grain_fps: float = 12.0


@dataclass(frozen=True, slots=True)
class NleMusic:
    path: str
    start_sec: float
    duration_sec: float
    gain_db: float = -18.0
    duck_ranges: tuple[tuple[float, float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class NleExtras:
    markers: tuple[NleMarker, ...] = ()
    titles: tuple[NleTitle, ...] = ()
    broll: tuple[NleBroll, ...] = ()
    color_filters: tuple[str, ...] = ()
    audio_filters: tuple[str, ...] = ()
    audio_stem: str = ""
    adjustments: tuple[NleAdjustment, ...] = ()
    music: tuple[NleMusic, ...] = ()
    captions: tuple[NleTitle, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


EMPTY = NleExtras()
