"""Context-driven transcript blocks.

This is the structural-chunking step separated from entity extraction. It keeps
complete sentences together, assigns story beats, and writes one inspectable
block manifest for the entity and storyboard passes.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.narrative import DEFAULT_BEATS, beat_for, blocks
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class TranscriptBlocksParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    beats: list[str] = Field(default_factory=lambda: list(DEFAULT_BEATS))
    min_block_words: int = Field(default=100, ge=20, le=1000)
    max_block_words: int = Field(default=300, ge=40, le=2000)
    max_blocks: int = Field(default=300, ge=1, le=1000)


@register_step
class TranscriptBlocksStep(BaseStep):
    type = "transcript.blocks"
    title = "Context blocks"
    description = (
        "Split the cleaned transcript into bounded context blocks and assign a "
        "narrative beat to each block without extracting entities."
    )
    status = "available"
    icon = "▤"
    color = "#22c55e"
    requires = ("transcribe",)
    produces = ("narrative_blocks",)
    params_model = TranscriptBlocksParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TranscriptBlocksParams.model_validate(params)
        discarded = set(context.discard_sentence_ids)
        sentences = [
            sentence for sentence in context.transcript if sentence.id not in discarded
        ]
        items = blocks(sentences, options.min_block_words, options.max_block_words)[
            : options.max_blocks
        ]
        payload = [
            {
                **item,
                "narrative_beat": beat_for(index, len(items), options.beats),
            }
            for index, item in enumerate(items)
        ]
        directory = context.output / "narrative"
        directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / "blocks.json"
        markdown_path = directory / "blocks.md"
        json_path.write_text(
            json.dumps(
                {"blocks": payload, "count": len(payload), "beats": options.beats},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        lines = ["# Context blocks", ""]
        for item in payload:
            lines.extend(
                [
                    f"## {item['context_block_id']} · {item['narrative_beat']}",
                    f"- Time: {item['start_sec']:.3f}s → {item['end_sec']:.3f}s",
                    f"- Sentences: {len(item['sentence_ids'])}",
                    "",
                    item["text"][:2000],
                    "",
                ]
            )
        markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        context.metadata["narrative_blocks"] = payload
        context.artifacts["narrative_blocks"] = str(json_path)
        context.artifacts["narrative_blocks_md"] = str(markdown_path)
        context.hashes["transcript.blocks"] = digest_payload(
            {"blocks": len(payload), "beats": options.beats}
        )
        io.report(100, f"{len(payload)} context block(s) mapped")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("narrative_blocks", "narrative_blocks_md")
            if context.artifacts.get(key)
        )
