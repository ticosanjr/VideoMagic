"""JSON format-preset catalog with shipped seeds."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from videoflow.domain.errors import AssetNotFoundError, InvalidConfigError
from videoflow.domain.formats import FormatDefinition
from videoflow.runtime import portable_home

_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*\.json$")

_SEEDS = {
    "vertical_9_16": FormatDefinition(
        format_id="vertical_9_16",
        name="YouTube Shorts / Reels 9:16",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        safe_zones={"bottom_px": 380.0, "right_px": 140.0},
        platforms=["youtube_shorts", "reels", "tiktok"],
        export_targets=["mp4_short", "fcpxml"],
        description="Vertical 1080x1920 with Shorts safe zones.",
        builtin=True,
    ),
    "feed_4_5": FormatDefinition(
        format_id="feed_4_5",
        name="Feed 4:5",
        aspect_ratio="4:5",
        width=1080,
        height=1350,
        safe_zones={"bottom_px": 220.0, "right_px": 80.0},
        platforms=["instagram_feed", "facebook_feed"],
        export_targets=["mp4_short"],
        description="Portrait feed format.",
        builtin=True,
    ),
    "square_1_1": FormatDefinition(
        format_id="square_1_1",
        name="Square 1:1",
        aspect_ratio="1:1",
        width=1080,
        height=1080,
        safe_zones={"bottom_px": 120.0, "right_px": 60.0},
        platforms=["instagram_feed", "linkedin"],
        export_targets=["mp4_short"],
        description="Square social format.",
        builtin=True,
    ),
    "landscape_16_9": FormatDefinition(
        format_id="landscape_16_9",
        name="Landscape 16:9",
        aspect_ratio="16:9",
        width=1920,
        height=1080,
        safe_zones={"bottom_px": 120.0, "right_px": 80.0},
        platforms=["youtube", "vimeo"],
        export_targets=["mp4_youtube", "fcpxml"],
        description="Longform landscape.",
        builtin=True,
    ),
}


def formats_dir() -> Path:
    directory = portable_home() / "formats"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write(path: Path, definition: FormatDefinition) -> None:
    payload = definition.model_dump(mode="json")
    payload["builtin"] = False
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def ensure_seeds() -> None:
    for definition in _SEEDS.values():
        path = formats_dir() / f"{definition.format_id}.json"
        if not path.is_file():
            _write(path, definition)


class FormatCatalog:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root).expanduser() if root is not None else formats_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        if root is None:
            ensure_seeds()

    def _items(self) -> dict[str, FormatDefinition]:
        items: dict[str, FormatDefinition] = {}
        for path in sorted(self.root.glob("*.json")):
            if not _FILENAME.match(path.name):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                definition = FormatDefinition.model_validate(payload)
            except (OSError, ValueError):
                continue
            if path.stem in _SEEDS:
                definition = definition.model_copy(update={"builtin": True})
            items[definition.format_id] = definition
        return items

    def list_payload(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self._items().values()]

    def get(self, format_id: str) -> FormatDefinition:
        item = self._items().get(format_id)
        if item is None:
            raise AssetNotFoundError(f"Unknown format: {format_id}")
        return item

    def save(self, definition: FormatDefinition) -> Path:
        if definition.format_id in _SEEDS:
            raise InvalidConfigError("Built-in formats cannot be overwritten; duplicate it")
        path = self.root / f"{definition.format_id}.json"
        _write(path, definition)
        return path

    def delete(self, format_id: str) -> bool:
        if format_id in _SEEDS:
            raise InvalidConfigError("Built-in formats cannot be deleted")
        path = self.root / f"{format_id}.json"
        if not path.is_file():
            return False
        path.unlink()
        return True

    def duplicate(self, format_id: str, new_id: str, *, name: str = "") -> FormatDefinition:
        source = self.get(format_id)
        definition = source.model_copy(
            update={
                "format_id": new_id,
                "name": name or f"{source.name} copy",
                "builtin": False,
            }
        )
        self.save(definition)
        return definition


def catalog() -> FormatCatalog:
    return FormatCatalog()


__all__ = ["FormatCatalog", "catalog", "ensure_seeds", "formats_dir"]
