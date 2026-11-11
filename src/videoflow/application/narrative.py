"""Shared narrative block and entity helpers.

The original ``narrative.beats`` step combined context chunking and entity
extraction. The long-form recipes now expose those as separate steps; keeping
the pure helpers here lets both the composite step and the split steps share the
same deterministic behavior.
"""

from __future__ import annotations

import re
from typing import Any

from videoflow.domain.state import Sentence

DEFAULT_BEATS = ("hook", "context", "conflict", "turning_point", "proof", "payoff")
METRIC = re.compile(
    r"(?:R\$\s*|\$\s*|€\s*|£\s*)?\d+(?:[.,]\d+)?\s*"
    r"(?:%|mil|milh(?:ão|ões)|bilh(?:ão|ões)|trilh(?:ão|ões)|"
    r"d[óo]lares|reais|euros|pontos)?",
    re.IGNORECASE,
)
PROPER = re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ]+(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+)+\b")
LOCATIONS = {
    "brasil",
    "estados unidos",
    "eua",
    "china",
    "europa",
    "ásia",
    "áfrica",
    "dubai",
    "são paulo",
    "rio de janeiro",
    "brasília",
    "londres",
    "nova york",
    "tóquio",
    "paris",
    "berlim",
}


def blocks(
    sentences: list[Sentence],
    minimum: int,
    maximum: int,
) -> list[dict[str, Any]]:
    """Split sentences into bounded context blocks without dropping text."""

    result: list[dict[str, Any]] = []
    current: list[Sentence] = []
    words = 0
    for sentence in sentences:
        count = len(sentence.text.split())
        if current and words + count > maximum:
            result.append(block(result, current))
            current = []
            words = 0
        current.append(sentence)
        words += count
        if words >= minimum:
            result.append(block(result, current))
            current = []
            words = 0
    if current:
        result.append(block(result, current))
    return result


def block(result: list[dict[str, Any]], sentences: list[Sentence]) -> dict[str, Any]:
    rate = 48_000
    return {
        "context_block_id": f"block_{len(result) + 1:03d}",
        "start_sample": min(sentence.start_sample for sentence in sentences),
        "end_sample": max(sentence.end_sample for sentence in sentences),
        "start_sec": round(min(sentence.start_sample for sentence in sentences) / rate, 3),
        "end_sec": round(max(sentence.end_sample for sentence in sentences) / rate, 3),
        "text": " ".join(sentence.text.strip() for sentence in sentences),
        "sentence_ids": [sentence.id for sentence in sentences],
    }


def beat_for(index: int, total: int, beats: list[str]) -> str:
    """Assign a narrative beat by relative position in the story."""

    if not beats:
        beats = list(DEFAULT_BEATS)
    if total <= 1:
        return beats[0]
    position = index / max(1, total - 1)
    boundaries = (0.1, 0.3, 0.5, 0.7, 0.9)
    slot = 0
    while slot < len(boundaries) and position > boundaries[slot]:
        slot += 1
    return beats[min(slot, len(beats) - 1)]


def extract_entities(
    text: str,
    object_keywords: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Deterministic entity pass used as the LLM fallback."""

    metrics = []
    for match in METRIC.finditer(text):
        value = match.group(0).strip()
        if not value:
            continue
        metrics.append(
            {
                "metric_name": "mentioned_value",
                "raw_value": value,
                "formatted_display": value,
                "chart_type": "kinetic_counter",
            }
        )
    people = [
        {
            "raw_mention": match.group(0),
            "canonical_name": match.group(0),
            "search_query": f"{match.group(0)} official photo",
        }
        for match in PROPER.finditer(text)
    ]
    locations = []
    lowered = text.casefold()
    for location in sorted(LOCATIONS):
        if location in lowered:
            locations.append(
                {
                    "location_name": location.title(),
                    "type": "geographic_city",
                    "action": "3d_map_flyover",
                }
            )
    objects = [
        {"object": keyword, "type": "mentioned_object", "action": "show_asset"}
        for keyword in object_keywords
        if keyword.casefold() in lowered
    ]
    return {
        "people": people,
        "physical_objects": objects,
        "data_metrics": metrics,
        "locations": locations,
    }
