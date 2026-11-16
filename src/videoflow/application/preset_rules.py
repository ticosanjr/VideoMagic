"""Channel preset rulebooks shared by steps, MCP, and the API."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from videoflow.application.settings import load_settings
from videoflow.domain.headless import PresetRulebook
from videoflow.runtime import portable_home


def channel_dir() -> Path:
    configured = load_settings().presets.channel_dir.strip()
    return Path(configured).expanduser() if configured else portable_home() / "channels"


def rule_id(text: str) -> str:
    return "rule-" + hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()[:12]


def normal(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def load_rulebook(channel_id: str) -> PresetRulebook:
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


def save_rulebook(book: PresetRulebook) -> Path:
    directory = channel_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{book.channel_id}.json"
    book.version += 1
    path.write_text(book.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path
