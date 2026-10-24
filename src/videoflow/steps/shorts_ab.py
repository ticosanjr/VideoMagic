"""Hook and duration A/B variants generated from selected Shorts."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class AbParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hooks: list[Literal["original", "repeat"]] = Field(
        default_factory=lambda: ["original", "repeat"]
    )
    duration_factors: list[float] = Field(default_factory=lambda: [1.0, 0.8])
    max_variants: int = Field(default=4, ge=1, le=20)


@register_step
class ShortsAbStep(BaseStep):
    type = "shorts.ab"
    title = "Hook and duration A/B"
    description = (
        "Clone each Short into hook and duration variants so the renderer can "
        "produce real A/B candidates."
    )
    status = "available"
    icon = "⚖"
    color = "#f59e0b"
    requires = ("shorts.select",)
    produces = ("ab_variants",)
    params_model = AbParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = AbParams.model_validate(params)
        if not context.selected_shorts:
            io.report(100, "No Shorts for A/B")
            return
        variants = []
        for clip in context.selected_shorts:
            for hook in options.hooks:
                for factor in options.duration_factors:
                    if len(variants) >= options.max_variants:
                        break
                    pieces = list(clip.pieces)
                    label = f"{hook}-{int(round(factor * 100))}"
                    if hook == "repeat" and clip.hook_start_sample is not None:
                        hook_piece = (
                            clip.hook_start_sample,
                            clip.hook_end_sample or clip.hook_start_sample,
                        )
                        if hook_piece[1] > hook_piece[0]:
                            pieces = [hook_piece, *pieces]
                    if factor < 1.0:
                        target = sum(end - start for start, end in pieces) * factor
                        trimmed: list[tuple[int, int]] = []
                        total = 0
                        for start, end in pieces:
                            length = end - start
                            if total + length >= target:
                                trimmed.append((start, start + int(target - total)))
                                break
                            trimmed.append((start, end))
                            total += length
                        pieces = trimmed
                    variants.append(
                        replace(
                            clip,
                            title=f"{clip.title} · {label}",
                            pieces=tuple(pieces),
                            start_sample=pieces[0][0],
                            end_sample=pieces[-1][1],
                            hook_text=clip.hook_text if hook == "repeat" else None,
                            hook_sentence_id=(
                                clip.hook_sentence_id if hook == "repeat" else None
                            ),
                            split_screen=False,
                        )
                    )
        context.selected_shorts = variants
        context.metadata["ab_variants"] = [
            {
                "title": clip.title,
                "pieces": [list(piece) for piece in clip.pieces],
                "duration_samples": sum(end - start for start, end in clip.pieces),
            }
            for clip in variants
        ]
        io.report(100, f"{len(variants)} A/B variant(s)")
