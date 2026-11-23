"""Content-cycle steps.

Implemented steps do real work. Planned steps are intentionally no-ops; the
runner marks them as skipped so a recipe can model the full workflow without
pretending a missing engine ran.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.adapters.ffmpeg.helpers import escape_ffmpeg_filter_path
from videoflow.application.titles import render_titles_ass
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import IngestError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class ColorGradeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lut_path: str = ""
    brightness: float = Field(default=0.0, ge=-1.0, le=1.0)
    contrast: float = Field(default=1.0, ge=0.1, le=4.0)
    saturation: float = Field(default=1.0, ge=0.0, le=4.0)
    gamma: float = Field(default=1.0, ge=0.1, le=4.0)

class TitlesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_lower_thirds: int = Field(default=40, ge=1, le=500)
    intro_title: str = ""
    outro_title: str = ""

class ThumbnailParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants: int = Field(default=1, ge=1, le=5)
    title: str = ""

@register_step
class ColorGradeStep(BaseStep):
    type = "color.grade"
    title = "Color / LUT"
    description = "Apply a .cube LUT and deterministic eq grade to the MP4 preview/render."
    status = "available"
    icon = "◐"
    color = "#22c55e"
    produces = ("color_grade",)
    params_model = ColorGradeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ColorGradeParams.model_validate(params)
        filters: list[str] = []
        lut = Path(options.lut_path).expanduser() if options.lut_path else None
        if lut is not None:
            if not lut.is_file():
                raise IngestError(f"LUT does not exist: {lut}")
            escaped = escape_ffmpeg_filter_path(lut)
            filters.append(f"lut3d='{escaped}'")
        if (
            options.brightness != 0.0
            or options.contrast != 1.0
            or options.saturation != 1.0
            or options.gamma != 1.0
        ):
            filters.append(
                "eq="
                f"brightness={options.brightness}:"
                f"contrast={options.contrast}:"
                f"saturation={options.saturation}:"
                f"gamma={options.gamma}"
            )
        target = context.output / "color" / "filters.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"filters": filters, "lut": str(lut) if lut else ""}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["color_filters"] = str(target)
        context.metadata["color_filters"] = filters
        io.report(100, f"{len(filters)} color filter(s) planned")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("color_filters")
        return (Path(path),) if path else ()

@register_step
class TitlesStep(BaseStep):
    type = "titles.plan"
    title = "Titles / graphics"
    description = "Plan title cards and speaker lower thirds from the timeline and Shorts."
    status = "available"
    icon = "T"
    color = "#22c55e"
    requires = ("edit.timeline",)
    produces = ("titles",)
    params_model = TitlesParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TitlesParams.model_validate(params)
        if context.state is None:
            raise IngestError("Titles require a validated timeline.")
        media = context.media
        fps = (media.fps_num / media.fps_den) if media is not None else 30.0
        transcript = context.state.transcript
        rate = media.audio_sample_rate if media is not None else 48000
        lower_thirds: list[dict[str, object]] = []
        previous_speaker: int | None = None
        for sentence in transcript:
            if sentence.speaker == previous_speaker:
                continue
            previous_speaker = sentence.speaker
            lower_thirds.append(
                {
                    "start_sec": round(sentence.start_sample / max(1, rate), 3),
                    "end_sec": round(
                        min(
                            sentence.end_sample / max(1, rate),
                            sentence.start_sample / max(1, rate) + 3.0,
                        ),
                        3,
                    ),
                    "speaker": sentence.speaker,
                    "text": f"Speaker {sentence.speaker + 1}",
                }
            )
            if len(lower_thirds) >= options.max_lower_thirds:
                break
        title_cards: list[dict[str, object]] = []
        if options.intro_title:
            title_cards.append(
                {
                    "kind": "intro",
                    "start_sec": 0.0,
                    "duration_sec": 2.0,
                    "text": options.intro_title,
                }
            )
        for index, short in enumerate(context.shorts):
            title_cards.append(
                {
                    "kind": "short",
                    "index": index,
                    "text": str(short.get("title") or f"Short {index + 1}"),
                }
            )
        if options.outro_title:
            duration = max(
                (clip.timeline_out_frame for clip in context.state.video_segments),
                default=0,
            ) / max(0.001, fps)
            title_cards.append(
                {
                    "kind": "outro",
                    "start_sec": round(max(0.0, duration - 2.0), 3),
                    "duration_sec": 2.0,
                    "text": options.outro_title,
                }
            )
        payload = {
            "ok": True,
            "lower_thirds": lower_thirds,
            "title_cards": title_cards,
        }
        target = context.output / "titles.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        context.artifacts["titles"] = str(target)
        media = context.media
        ass_path = render_titles_ass(
            payload,
            context.output / "titles.ass",
            width=media.width if media is not None else 1920,
            height=media.height if media is not None else 1080,
        )
        context.artifacts["titles_ass"] = str(ass_path)
        context.metadata["titles"] = payload
        io.report(100, f"{len(lower_thirds)} lower third(s), {len(title_cards)} title card(s)")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("titles")
        return (Path(path),) if path else ()

@register_step
class ThumbnailStep(BaseStep):
    type = "thumbnail.generate"
    title = "Thumbnail / cover"
    description = "Render one or more thumbnail candidates from the source."
    status = "available"
    icon = "▣"
    color = "#22c55e"
    requires = ("ingest",)
    params_model = ThumbnailParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ThumbnailParams.model_validate(params)
        if context.media is None:
            raise IngestError("Thumbnail requires ingested media.")
        duration = (
            context.media.duration_frames
            * context.media.fps_den
            / max(1, context.media.fps_num)
        )
        fractions = [0.5, 0.35, 0.65, 0.2, 0.8]
        targets: list[str] = []
        adapter = FFmpegAdapter()
        for index in range(options.variants):
            target = context.output / "thumbnails" / f"thumbnail-{index + 1}.png"
            adapter.render_thumbnail(
                Path(context.source),
                target,
                time_sec=max(0.0, duration * fractions[index % len(fractions)]),
            )
            targets.append(str(target))
            context.artifacts[f"thumbnail_{index + 1}"] = str(target)
            io.report(
                int((index + 1) / options.variants * 100),
                f"Thumbnail {index + 1}/{options.variants}",
            )
        context.artifacts["thumbnail"] = targets[0]
        context.metadata["thumbnails"] = targets
        if options.title:
            context.metadata["thumbnail_title"] = options.title

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        paths = [Path(path) for path in context.metadata.get("thumbnails", [])]
        return tuple(paths)

