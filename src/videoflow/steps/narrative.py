"""Narrative beat mapping and entity extraction for the master recipe."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.state import Sentence
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step

_DEFAULT_BEATS = ("hook", "context", "conflict", "turning_point", "proof", "payoff")
_METRIC = re.compile(
    r"(?:R\$\s*|\$\s*|€\s*|£\s*)?\d+(?:[.,]\d+)?\s*"
    r"(?:%|mil|milh(?:ão|ões)|bilh(?:ão|ões)|trilh(?:ão|ões)|"
    r"d[óo]lares|reais|euros|pontos)?",
    re.IGNORECASE,
)
_PROPER = re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ]+(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+)+\b")
_LOCATIONS = {
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


class NarrativeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    beats: list[str] = Field(default_factory=lambda: list(_DEFAULT_BEATS))
    min_block_words: int = Field(default=100, ge=20, le=1000)
    max_block_words: int = Field(default=300, ge=40, le=2000)
    object_keywords: list[str] = Field(default_factory=list)
    max_blocks: int = Field(default=300, ge=1, le=1000)


def _blocks(sentences: list[Sentence], minimum: int, maximum: int) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: list[Sentence] = []
    words = 0
    for sentence in sentences:
        count = len(sentence.text.split())
        if current and words + count > maximum:
            blocks.append(_block(blocks, current))
            current = []
            words = 0
        current.append(sentence)
        words += count
        if words >= minimum:
            blocks.append(_block(blocks, current))
            current = []
            words = 0
    if current:
        blocks.append(_block(blocks, current))
    return blocks


def _block(blocks: list[dict[str, Any]], sentences: list[Sentence]) -> dict[str, Any]:
    rate = 48_000
    return {
        "context_block_id": f"block_{len(blocks) + 1:03d}",
        "start_sample": min(sentence.start_sample for sentence in sentences),
        "end_sample": max(sentence.end_sample for sentence in sentences),
        "start_sec": round(min(sentence.start_sample for sentence in sentences) / rate, 3),
        "end_sec": round(max(sentence.end_sample for sentence in sentences) / rate, 3),
        "text": " ".join(sentence.text.strip() for sentence in sentences),
        "sentence_ids": [sentence.id for sentence in sentences],
    }


def _beat_for(index: int, total: int, beats: list[str]) -> str:
    if not beats:
        beats = list(_DEFAULT_BEATS)
    if total <= 1:
        return beats[0]
    position = index / max(1, total - 1)
    boundaries = (0.1, 0.3, 0.5, 0.7, 0.9)
    slot = 0
    while slot < len(boundaries) and position > boundaries[slot]:
        slot += 1
    return beats[min(slot, len(beats) - 1)]


def _entities(text: str, object_keywords: list[str]) -> dict[str, list[dict[str, Any]]]:
    metrics = []
    for match in _METRIC.finditer(text):
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
        for match in _PROPER.finditer(text)
    ]
    locations = []
    lowered = text.casefold()
    for location in sorted(_LOCATIONS):
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


@register_step
class NarrativeBeatsStep(BaseStep):
    type = "narrative.beats"
    title = "Narrative beats"
    description = (
        "Split the transcript into context blocks, assign story beats, and extract "
        "people, objects, metrics, and locations."
    )
    status = "available"
    icon = "◈"
    color = "#a78bfa"
    requires = ("transcribe",)
    produces = ("narrative_beats", "narrative_entities")
    params_model = NarrativeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = NarrativeParams.model_validate(params)
        if not context.transcript:
            context.metadata["narrative_beats"] = []
            io.report(100, "No transcript; narrative skipped")
            return
        discarded = set(context.discard_sentence_ids)
        sentences = [
            sentence for sentence in context.transcript if sentence.id not in discarded
        ]
        blocks = _blocks(
            sentences,
            options.min_block_words,
            options.max_block_words,
        )[: options.max_blocks]
        payload: list[dict[str, Any]] = []
        for index, block in enumerate(blocks):
            payload.append(
                {
                    **block,
                    "narrative_beat": _beat_for(index, len(blocks), options.beats),
                    "extracted_entities": _entities(
                        block["text"], options.object_keywords
                    ),
                }
            )
        if options.provider_id and io.llm_client is not None:
            try:
                prompt = self._prompt(payload, options.beats)
                response = io.llm_client.complete_json(
                    prompt, "videoflow.narrative"
                )
                payload = self._merge_model(payload, response)
            except Exception as exc:  # noqa: BLE001 - keep deterministic fallback
                context.warnings.append(
                    f"Narrative model fallback to deterministic beats: {exc}"
                )
        context.metadata["narrative_beats"] = payload
        directory = context.output / "narrative"
        directory.mkdir(parents=True, exist_ok=True)
        beats_path = directory / "beats.json"
        entities_path = directory / "entities.json"
        beats_path.write_text(
            json.dumps({"blocks": payload}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        entities_path.write_text(
            json.dumps(
                {
                    "blocks": [
                        {
                            "context_block_id": block["context_block_id"],
                            "timecode_range": {
                                "start": block["start_sec"],
                                "end": block["end_sec"],
                            },
                            "narrative_beat": block["narrative_beat"],
                            "extracted_entities": block["extracted_entities"],
                        }
                        for block in payload
                    ]
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["narrative_beats"] = str(beats_path)
        context.artifacts["narrative_entities"] = str(entities_path)
        context.hashes["narrative.beats"] = digest_payload(
            {"blocks": len(payload), "beats": options.beats}
        )
        io.report(100, f"{len(payload)} context block(s) mapped")

    @staticmethod
    def _prompt(blocks: list[dict[str, Any]], beats: list[str]) -> str:
        return (
            "You are a narrative editor. For each context block, return JSON "
            '{"blocks":[{"context_block_id":"...","narrative_beat":"...",'
            '"extracted_entities":{"people":[],"physical_objects":[],'
            '"data_metrics":[],"locations":[]}}]}. '
            f"Allowed beats: {', '.join(beats)}. Keep the same block ids and do "
            "not invent facts. Blocks:\n"
            + json.dumps(
                [
                    {
                        "context_block_id": block["context_block_id"],
                        "text": block["text"],
                    }
                    for block in blocks
                ],
                ensure_ascii=False,
            )
        )

    @staticmethod
    def _merge_model(
        blocks: list[dict[str, Any]], response: dict[str, Any]
    ) -> list[dict[str, Any]]:
        by_id = {
            str(item.get("context_block_id")): item
            for item in response.get("blocks", [])
            if isinstance(item, dict)
        }
        merged: list[dict[str, Any]] = []
        for block in blocks:
            model = by_id.get(str(block["context_block_id"]))
            if not model:
                merged.append(block)
                continue
            entities = model.get("extracted_entities")
            merged.append(
                {
                    **block,
                    "narrative_beat": str(
                        model.get("narrative_beat", block["narrative_beat"])
                    ),
                    "extracted_entities": entities
                    if isinstance(entities, dict)
                    else block["extracted_entities"],
                }
            )
        return merged

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(path)
            for path in (
                context.artifacts.get("narrative_beats"),
                context.artifacts.get("narrative_entities"),
            )
            if path
        )
