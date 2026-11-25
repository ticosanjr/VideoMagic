"""Long-form captions written as an ASS sidecar and a merged burn-in file."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.caption_presets import apply_preset
from videoflow.application.captions import (
    CaptionLine,
    _normalize_caption_lines,
    build_ass_lines,
    caption_lines,
    filter_caption_sentences,
    merge_ass_files,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import ExportError
from videoflow.domain.state import ProjectState, Sentence
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class EmptyAssEventsError(ExportError):
    """Cues existed but the ASS writer produced no Dialogue lines."""

    code = "empty_ass_events"


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


def _timeline_pieces(state: ProjectState | None, fallback_end: int) -> list[tuple[int, int]]:
    """Return active source ranges in timeline order for caption mapping."""

    segments = state.audio_segments if state is not None else []
    if not segments:
        return [(0, max(1, fallback_end))]
    pieces = [
        (int(clip.source_in_sample), int(clip.source_out_sample))
        for clip in sorted(segments, key=lambda item: item.timeline_in_sample)
        if clip.source_out_sample > clip.source_in_sample
    ]
    return pieces or [(0, max(1, fallback_end))]


def _kept_source_ranges(context: PipelineContext) -> list[tuple[int, int]]:
    """Convert kept video segments to source-sample ranges for word filtering."""

    state = context.state
    media = context.media
    if state is None or media is None or not state.video_segments:
        return []
    timebase = media.timebase()
    ranges: list[tuple[int, int]] = []
    for clip in state.video_segments:
        start = timebase.frame_start_sample(clip.source_in_frame)
        end = timebase.frame_start_sample(clip.source_out_frame)
        if end > start:
            ranges.append((start, end))
    return ranges


def _discard_ids(context: PipelineContext) -> set[int]:
    ids = set(context.discard_sentence_ids)
    if context.state is not None:
        ids.update(context.state.pipeline.discard_sentence_ids)
    return ids


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
                update={"style": apply_preset(options.preset, _long_form_style(options.style))}
            )
        else:
            options = options.model_copy(update={"style": _long_form_style(options.style)})
        if not options.enabled:
            context.metadata["captions_disabled"] = True
            io.report(100, "Caption generation disabled")
            return
        transcript = _caption_sentences(context)
        transcript = filter_caption_sentences(
            transcript,
            discard_ids=_discard_ids(context),
            kept_source_ranges=_kept_source_ranges(context),
        )
        if not transcript:
            context.warnings.append("Captions skipped: the transcript is empty.")
            io.report(100, "No transcript; captions skipped")
            return
        sample_rate = context.media.audio_sample_rate if context.media is not None else 48000
        end_sample = max((sentence.end_sample for sentence in transcript), default=0)
        if end_sample <= 0:
            end_sample = max(1, sample_rate)
        lines = caption_lines(
            transcript,
            _timeline_pieces(context.state, end_sample),
            sample_rate=sample_rate,
            word_timing=options.style.word_timing,
            effect=options.style.effect,
            max_words=0,
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
        cues = _normalize_caption_lines(split)
        if not cues:
            raise EmptyAssEventsError(
                f"{len(split)} cue(s) collapsed to zero timed captions"
            )
        captions_path = directory / "captions.ass"
        ass_text = build_ass_lines(
            cues,
            style=options.style,
            width=options.width,
            height=options.height,
        )
        dialogue_count = sum(
            1 for line in ass_text.splitlines() if line.startswith("Dialogue:")
        )
        if dialogue_count < len(cues):
            raise EmptyAssEventsError(
                f"captions.ass has {dialogue_count} Dialogue line(s) for "
                f"{len(cues)} cue(s)"
            )
        captions_path.write_text(ass_text, encoding="utf-8")
        captions_srt = directory / "captions.srt"
        captions_srt.write_text(_srt(cues), encoding="utf-8")
        merged_path = context.output / "subtitles.ass"
        merge_ass_files([context.output / "titles.ass", captions_path], merged_path)
        context.artifacts["captions"] = str(captions_path)
        context.artifacts["captions_ass"] = str(captions_path)
        context.artifacts["captions_srt"] = str(captions_srt)
        context.artifacts["subtitles_ass"] = str(merged_path)
        context.hashes["captions.plan"] = digest_payload(
            {"lines": len(split), "chars": options.max_chars}
        )
        io.report(100, f"{len(split)} caption line(s) written")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("captions_ass", "captions_srt", "subtitles_ass")
            if context.artifacts.get(key)
        )


def _caption_sentences(context: PipelineContext) -> list[Sentence]:
    """Prefer context words, then the persisted clean transcript."""

    sentences = list(context.transcript)
    if any(sentence.words for sentence in sentences):
        return sentences
    candidates: list[Path] = []
    artifact = context.artifacts.get("transcript_clean")
    if artifact:
        candidates.append(Path(str(artifact)))
    candidates.extend(
        (
            context.output / "transcript" / "transcript_clean.json",
            context.work / "transcript_clean.json",
        )
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            loaded = [Sentence.model_validate(item) for item in payload]
        except (OSError, ValueError, TypeError):
            continue
        if loaded and any(sentence.words for sentence in loaded):
            context.transcript = loaded
            context.warnings.append(
                f"Captions loaded word timings from {path.name}"
            )
            return loaded
    return sentences


def _srt_time(seconds: float) -> str:
    total = max(0, round(seconds * 1000))
    hours, remainder = divmod(total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _srt(lines: list[CaptionLine]) -> str:
    blocks = []
    for index, line in enumerate(lines, start=1):
        blocks.append(f"{index}\n{_srt_time(line.start)} --> {_srt_time(line.end)}\n{line.text}\n")
    return "\n".join(blocks)


__all__ = ["CaptionsPlanParams", "CaptionsPlanStep"]
