"""Load shipped presets and persist operator presets atomically."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from videoflow.application.storage import atomic_write_text
from videoflow.domain.errors import InvalidPresetNameError, PresetError, PresetNotFoundError
from videoflow.domain.presets import load_preset, load_shipped_presets, shipped_preset_dir
from videoflow.domain.state import Preset
from videoflow.runtime import portable_home

PresetSource = Literal["shipped", "operator"]
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True, slots=True)
class PresetEntry:
    preset: Preset
    source: PresetSource
    path: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.preset.name,
            "description": self.preset.description,
            "source": self.source,
            "modules_config": self.preset.modules_config.model_dump(mode="json"),
            "module_enabled": self.preset.module_enabled.model_dump(mode="json"),
        }


def operator_preset_dir() -> Path:
    return portable_home() / "presets"


def validate_preset_name(name: str) -> str:
    if not _NAME.fullmatch(name):
        raise InvalidPresetNameError(
            f"Preset names must match [a-z0-9][a-z0-9-]{{0,63}}: {name}"
        )
    return name


def load_presets() -> tuple[PresetEntry, ...]:
    """Return shipped presets, with operator files taking precedence by name."""

    entries: dict[str, PresetEntry] = {}
    for preset in load_shipped_presets():
        entries[preset.name] = PresetEntry(
            preset=preset,
            source="shipped",
            path=shipped_preset_dir() / f"{preset.name}.json",
        )
    operator = operator_preset_dir()
    if operator.is_dir():
        for path in sorted(operator.glob("*.json")):
            try:
                preset = load_preset(path)
            except (OSError, ValueError) as exc:
                raise PresetError(f"Cannot load preset {path.name}: {exc}") from exc
            entries[preset.name] = PresetEntry(preset=preset, source="operator", path=path)
    return tuple(entries[name] for name in sorted(entries))


def get_preset(name: str) -> PresetEntry:
    validate_preset_name(name)
    for entry in load_presets():
        if entry.preset.name == name:
            return entry
    raise PresetNotFoundError(name)


def save_preset(name: str, payload: dict[str, Any]) -> PresetEntry:
    """Validate and atomically write an operator preset.

    The file keeps the caller's partial keys so future defaults still apply.
    """

    validate_preset_name(name)
    body = dict(payload)
    body["name"] = name
    try:
        preset = Preset.model_validate(body)
    except ValueError as exc:
        raise PresetError(f"Invalid preset {name}: {exc}") from exc
    directory = operator_preset_dir()
    path = directory / f"{name}.json"
    atomic_write_text(path, json.dumps(body, indent=2, ensure_ascii=False) + "\n")
    return PresetEntry(preset=preset, source="operator", path=path)
