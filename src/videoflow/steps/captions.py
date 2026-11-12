"""Long-form captions written as an ASS sidecar and a merged burn-in file."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.caption_presets import apply_preset
from videoflow.application.captions import (
    CaptionLine,
    build_ass_lines,
    caption_lines,
    merge_ass_files,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class CaptionsPlanParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    preset: str = ""
    max_chars: int = Field(default=42, ge=12, le=120)
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    style: CaptionStyle = Field(default_factory=CaptionStyle)


def _long_form_style(style: CaptionStyle) -> CaptionStyle:
    return style.model_copy(
        update={
            "font_size": 46 if style.font_size == 72 else style.font_size,
            "position_y": 0.88 if style.position_y == 0.78 else style.position_y,
            "max_width": 0.86,
            "alignment": 2,
        }
    )


def _split_line(line: CaptionLine, max_chars: int) -> list[CaptionLine]:
    if len(line.text) <= max_chars:
        return [line]
    tokens = line.text.split()
    if len(tokens) <= 1:
        return [line]
    chunks: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        candidate = " ".join([*current, token])
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = [token]
        else:
            current.append(token)
    if current:
        chunks.append(current)
    if len(chunks) <= 1:
        return [line]
    weights = [max(1, len(" ".join(chunk))) for chunk in chunks]
    total = sum(weights)
    result: list[CaptionLine] = []
    cursor = line.start
    for index, (chunk, weight) in enumerate(zip(chunks, weights, strict=True)):
        end = (
            line.end
            if index == len(chunks) - 1
            else cursor + (line.end - line.start) * weight / total
        )
        result.append(
            CaptionLine(
                start=cursor,
                end=end,
                text=" ".join(chunk),
                speaker=line.speaker,
            )
        )
        cursor = end
    return result


@register_step
class CaptionsPlanStep(BaseStep):
    type = "captions.plan"
    title = "Long-form captions"
    description = (
        "Write sentence captions from the transcript, merge them with the titles "
        "ASS, and expose a burn-in sidecar for the video export."
    )
    status = "available"
    icon = "CC"
    color = "#22c55e"
    params_model = CaptionsPlanParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = CaptionsPlanParams.model_validate(params)
        if options.preset:
            options = options.model_copy(
                update={
                    "style": apply_preset(
                        options.preset, _long_form_style(options.style)
                    )
                }
            )
        else:
            options = options.model_copy(
                update={"style": _long_form_style(options.style)}
            )
        if not options.enabled:
            context.metadata["captions_disabled"] = True
            io.report(100, "Caption generation disabled")
            return
        if not context.transcript:
            context.warnings.append("Captions skipped: the transcript is empty.")
            io.report(100, "No transcript; captions skipped")
            return
        sample_rate = (
            context.media.audio_sample_rate if context.media is not None else 48000
        )
        end_sample = max(
            (sentence.end_sample for sentence in context.transcript), default=0
        )
        if end_sample <= 0:
            end_sample = max(1, sample_rate)
        lines = caption_lines(
            context.transcript,
            [(0, end_sample)],
            sample_rate=sample_rate,
            word_timing=options.style.word_timing,
            warnings=context.warnings,
        )
        split: list[CaptionLine] = []
        for line in lines:
            split.extend(_split_line(line, options.max_chars))
        if not split:
            context.warnings.append("Captions skipped: no timed sentences.")
            io.report(100, "No timed captions")
            return
        directory = context.output / "captions"
        directory.mkdir(parents=True, exist_ok=True)
        captions_path = directory / "captions.ass"
        captions_path.write_text(
            build_ass_lines(
                split,
                style=options.style,
                width=options.width,
                height=options.height,
            ),
            encoding="utf-8",
        )
        merged_path = context.output / "subtitles.ass"
        merge_ass_files(
            [context.output / "titles.ass", captions_path], merged_path
        )
        context.artifacts["captions"] = str(captions_path)
        context.artifacts["captions_ass"] = str(captions_path)
        context.artifacts["subtitles_ass"] = str(merged_path)
        context.hashes["captions.plan"] = digest_payload(
            {"lines": len(split), "chars": options.max_chars}
        )
        io.report(100, f"{len(split)} caption line(s) written")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("captions_ass", "subtitles_ass")
            if context.artifacts.get(key)
        )


__all__ = ["CaptionsPlanParams", "CaptionsPlanStep"]
