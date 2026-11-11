from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import Sentence
from videoflow.steps.base import StepIO
from videoflow.steps.transcript_blocks import (
    TranscriptBlocksParams,
    TranscriptBlocksStep,
)


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir(parents=True)
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_transcript_blocks_assigns_beats_and_excludes_discards(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    context.transcript = [
        Sentence(
            id=0,
            start_sample=0,
            end_sample=48_000,
            text="First complete sentence with some context.",
        ),
        Sentence(
            id=1,
            start_sample=48_000,
            end_sample=96_000,
            text="Second sentence contains the main conflict.",
        ),
        Sentence(
            id=2,
            start_sample=96_000,
            end_sample=144_000,
            text="Discarded false start.",
        ),
    ]
    context.discard_sentence_ids = [2]
    context.metadata["variables"] = {"topic": "Test"}

    TranscriptBlocksStep().run(
        context,
        TranscriptBlocksParams(min_block_words=20, max_block_words=50),
        StepIO(),
    )

    payload = json.loads(
        (context.output / "narrative" / "blocks.json").read_text(encoding="utf-8")
    )
    assert payload["count"] == 1
    block = payload["blocks"][0]
    assert block["context_block_id"] == "block_001"
    assert block["sentence_ids"] == [0, 1]
    assert block["narrative_beat"] in {"hook", "context", "conflict"}
    assert "Discarded" not in block["text"]
    assert context.artifacts["narrative_blocks"].endswith("narrative/blocks.json")
