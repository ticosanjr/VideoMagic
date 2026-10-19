"""Load shipped and operator presets. Files are data; they are validated before use."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.domain.state import Preset

SHIPPED_PRESET_NAMES: tuple[str, ...] = (
    "lecture-clean",
    "shorts-aggressive",
    "youtube-talking-head",
)


def shipped_preset_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "presets"


def load_preset(path: Path) -> Preset:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Preset.model_validate(data)


def load_shipped_presets() -> tuple[Preset, ...]:
    directory = shipped_preset_dir()
    paths = sorted(directory.glob("*.json"))
    return tuple(load_preset(path) for path in paths)
