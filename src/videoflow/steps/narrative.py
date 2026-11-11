"""Narrative beat mapping and entity extraction for the master recipe."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.narrative import (
    DEFAULT_BEATS as _DEFAULT_BEATS,
)
from videoflow.application.narrative import (
    beat_for as _beat_for,
)
from videoflow.application.narrative import (
    blocks as _blocks,
)
from videoflow.application.narrative import (
    extract_entities as _entities,
)
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class NarrativeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = ""
    beats: list[str] = Field(default_factory=lambda: list(_DEFAULT_BEATS))
    min_block_words: int = Field(default=100, ge=20, le=1000)
    max_block_words: int = Field(default=300, ge=40, le=2000)
    object_keywords: list[str] = Field(default_factory=list)
    max_blocks: int = Field(default=300, ge=1, le=1000)


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
