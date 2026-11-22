"""Single JSON-object parser for all OpenAI-compatible providers."""

from __future__ import annotations

import json
from typing import Any


def parse_json_object(content: str) -> dict[str, Any]:
    """Parse a JSON object from plain text, fences, or surrounding prose."""

    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) < 3:
            raise ValueError("unterminated JSON fence")
        text = "\n".join(lines[1:-1]).strip()
    elif "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


__all__ = ["parse_json_object"]
