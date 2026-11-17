"""Channel preset rulebooks backed by the canonical Markdown style catalog."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.settings import load_settings
from videoflow.application.style_catalog import (
    catalog as style_catalog,
)
from videoflow.application.style_catalog import (
    normal,
    rule_id,
    rulebook_from_style,
    style_from_rulebook,
    styles_dir,
)
from videoflow.domain.errors import StyleNotFoundError
from videoflow.domain.headless import PresetRulebook
from videoflow.runtime import portable_home

__all__ = [
    "channel_dir",
    "load_rulebook",
    "normal",
    "rule_id",
    "save_rulebook",
    "style_dir",
]


def style_dir() -> Path:
    return styles_dir()


def channel_dir() -> Path:
    """Legacy JSON rulebook directory kept only for migration reads."""

    configured = load_settings().presets.channel_dir.strip()
    return Path(configured).expanduser() if configured else portable_home() / "channels"


def _load_legacy(channel_id: str) -> PresetRulebook:
    path = channel_dir() / f"{channel_id}.json"
    if not path.is_file():
        return PresetRulebook(channel_id=channel_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return PresetRulebook(channel_id=channel_id)
    if not isinstance(payload, dict):
        return PresetRulebook(channel_id=channel_id)
    if "rules" in payload and "learned_rules" not in payload:
        payload["learned_rules"] = payload.pop("rules")
    payload.setdefault("schema_version", 2)
    try:
        return PresetRulebook.model_validate(payload)
    except ValueError:
        return PresetRulebook(channel_id=channel_id)


def load_rulebook(channel_id: str) -> PresetRulebook:
    try:
        return rulebook_from_style(style_catalog().get(channel_id))
    except StyleNotFoundError:
        return _load_legacy(channel_id)


def save_rulebook(book: PresetRulebook) -> Path:
    book.version += 1
    style_id = book.channel_id or "default"
    try:
        existing = style_catalog().get(style_id)
    except StyleNotFoundError:
        existing = None
    style = style_from_rulebook(book, existing=existing, style_id=style_id)
    return style_catalog().save(style)
