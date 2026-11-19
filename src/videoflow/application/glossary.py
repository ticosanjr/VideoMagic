"""Per-channel glossary for PT-BR + English technical terms."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from videoflow.application.brand_kit import brand_kit_root

DEFAULT_TERMS: tuple[dict[str, Any], ...] = (
    {"canonical": "Claude", "variants": ["clódi", "clodi", "claude"]},
    {"canonical": "MCP", "variants": ["emecêpê", "emecepe", "mcp"]},
    {"canonical": "OpenCode", "variants": ["open code", "opencode", "opencodi"]},
    {"canonical": "NVIDIA", "variants": ["invídia", "invidia", "envidia", "nvidia"]},
    {"canonical": "Jensen Huang", "variants": ["jensen huang", "jensen"]},
    {"canonical": "NVENC", "variants": ["nvenc", "envic"]},
    {"canonical": "Whisper", "variants": ["whisper", "uisper"]},
    {"canonical": "CUDA", "variants": ["cuda", "cudá"]},
    {"canonical": "DaVinci Resolve", "variants": ["davinci resolve", "da vinci"]},
    {"canonical": "Kdenlive", "variants": ["kdenlive"]},
    {"canonical": "CTranslate2", "variants": ["ctranslate2", "c translate 2"]},
    {"canonical": "ONNX", "variants": ["onnx", "onix"]},
    {"canonical": "MediaPipe", "variants": ["mediapipe", "media pipe"]},
    {"canonical": "Tailscale", "variants": ["tailscale", "tail scale"]},
)


def glossary_path(channel_id: str) -> Path:
    return brand_kit_root(channel_id) / "glossary.json"


def _read(channel_id: str) -> dict[str, Any]:
    path = glossary_path(channel_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema_version": 1, "channel_id": channel_id, "terms": []}
    if not isinstance(payload, dict):
        return {"schema_version": 1, "channel_id": channel_id, "terms": []}
    payload.setdefault("schema_version", 1)
    payload.setdefault("channel_id", channel_id)
    if not isinstance(payload.get("terms"), list):
        payload["terms"] = []
    return payload


def _normalize_term(value: dict[str, Any]) -> dict[str, Any] | None:
    canonical = str(value.get("canonical") or "").strip()
    if not canonical:
        return None
    variants = value.get("variants")
    if not isinstance(variants, list):
        variants = []
    cleaned = []
    for item in variants:
        text = str(item).strip()
        if text and text.casefold() != canonical.casefold() and text not in cleaned:
            cleaned.append(text)
    return {
        "canonical": canonical,
        "variants": cleaned,
        "phonetic": str(value.get("phonetic") or ""),
        "case_sensitive": bool(value.get("case_sensitive", False)),
        "language": str(value.get("language") or "pt"),
    }


def load_glossary(channel_id: str = "") -> dict[str, Any]:
    payload = _read(channel_id)
    terms: dict[str, dict[str, Any]] = {}
    for item in DEFAULT_TERMS:
        normalized = _normalize_term(item)
        if normalized:
            terms[normalized["canonical"].casefold()] = normalized
    for item in payload["terms"]:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_term(item)
        if not normalized:
            continue
        key = normalized["canonical"].casefold()
        existing = terms.get(key)
        if existing is None:
            terms[key] = normalized
        else:
            merged = list(existing["variants"])
            for variant in normalized["variants"]:
                if variant not in merged:
                    merged.append(variant)
            existing["variants"] = merged
    ordered = sorted(terms.values(), key=lambda item: item["canonical"].casefold())
    return {
        "ok": True,
        "channel_id": channel_id,
        "path": str(glossary_path(channel_id)),
        "terms": ordered,
        "count": len(ordered),
    }


def upsert_glossary(channel_id: str, terms: list[dict[str, Any]]) -> dict[str, Any]:
    payload = _read(channel_id)
    current = {
        str(item.get("canonical") or "").casefold(): item
        for item in payload["terms"]
        if isinstance(item, dict)
    }
    for item in terms:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_term(item)
        if normalized is None:
            continue
        current[normalized["canonical"].casefold()] = normalized
    payload["terms"] = list(current.values())
    payload["channel_id"] = channel_id
    path = glossary_path(channel_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return load_glossary(channel_id)


def apply_glossary(text: str, terms: list[dict[str, Any]]) -> tuple[str, int]:
    corrected = str(text or "")
    applied = 0
    for term in terms:
        if not isinstance(term, dict):
            continue
        canonical = str(term.get("canonical") or "").strip()
        if not canonical:
            continue
        variants = term.get("variants")
        if not isinstance(variants, list):
            continue
        case_sensitive = bool(term.get("case_sensitive", False))
        flags = 0 if case_sensitive else re.IGNORECASE
        for variant in sorted(
            (str(item).strip() for item in variants if str(item).strip()),
            key=len,
            reverse=True,
        ):
            pattern = re.compile(rf"(?<!\w){re.escape(variant)}(?!\w)", flags)
            corrected, count = pattern.subn(canonical, corrected)
            applied += count
    return corrected, applied


__all__ = [
    "DEFAULT_TERMS",
    "apply_glossary",
    "glossary_path",
    "load_glossary",
    "upsert_glossary",
]
