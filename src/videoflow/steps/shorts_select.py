"""Short-clip selection step."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from pydantic import BaseModel

from videoflow.application.audio_analysis import detect_audio_energy
from videoflow.application.retakes import cull_intervals
from videoflow.application.shorts import (
    previous_shorts_from_report,
    select_shorts,
    short_dimensions,
)
from videoflow.application.video_analysis import detect_scene_changes, scene_intervals
from videoflow.core.context import PipelineContext
from videoflow.domain.config import ShortsConfig
from videoflow.domain.errors import IngestError
from videoflow.domain.timebase import Rounding
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step


@register_step
class ShortsSelectStep(BaseStep):
    type = "shorts.select"
    title = "Select Shorts"
    description = (
        "Score and select vertical clips from the transcript, audio energy, and scene changes."
    )
    requires = ("transcribe",)
    produces = ("shorts",)
    params_model = ShortsConfig

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ShortsConfig.model_validate(params)
        media = require_media(context)
        if not context.transcript:
            raise IngestError(
                "Shorts require a transcript. Provide an SRT or enable transcription."
            )
        timebase = media.timebase()
        minimum = timebase.seconds_to_samples(
            Fraction(options.target_duration_min_sec), Rounding.NEAREST
        )
        maximum = timebase.seconds_to_samples(
            Fraction(options.target_duration_max_sec), Rounding.NEAREST
        )
        discard = set(context.discard_sentence_ids)
        cuts = cull_intervals(context.transcript, context.discard_sentence_ids)
        kept = [item for item in context.transcript if item.id not in discard]
        range_start = timebase.seconds_to_samples(
            Fraction(str(options.source_start_sec)), Rounding.NEAREST
        )
        range_end = (
            timebase.seconds_to_samples(
                Fraction(str(options.source_end_sec)), Rounding.NEAREST
            )
            if options.source_end_sec is not None
            else context.duration_samples()
        )
        kept = [
            item
            for item in kept
            if item.start_sample >= range_start and item.end_sample <= range_end
        ]
        width, height = short_dimensions(options.aspect_ratio, options.resolution)
        previous = (
            previous_shorts_from_report(context.output / "shorts.json")
            if options.prompt_mode == "refine"
            else []
        )
        warnings = context.warnings
        energy: tuple[tuple[int, int], ...] = ()
        scenes: tuple[tuple[int, int], ...] = ()
        if options.scene_change_boost:
            try:
                scenes = tuple(
                    scene_intervals(
                        detect_scene_changes(Path(context.source)),
                        sample_rate=media.audio_sample_rate,
                    )
                )
            except IngestError as exc:
                warnings.append(f"Scene analysis skipped: {exc.message}")
        if options.audio_energy_boost:
            try:
                energy = tuple(
                    detect_audio_energy(Path(context.source), media.audio_sample_rate)
                )
            except IngestError as exc:
                warnings.append(f"Audio energy analysis skipped: {exc.message}")

        io.report(20, "Selecting social clips")
        selected = select_shorts(
            kept,
            min_samples=minimum,
            max_samples=maximum,
            count=max(1, options.max_clips_to_generate),
            min_clips=options.min_clips,
            selection_mode=options.selection_mode,
            sample_rate=media.audio_sample_rate,
            cuts=cuts,
            client=io.llm_client,
            warnings=warnings,
            prompt=options.prompt,
            reprompt=options.reprompt,
            prompt_mode=options.prompt_mode,
            previous=previous,
            hook_mode=options.hook_mode,
            remove_fillers=options.remove_fillers,
            filler_words=options.filler_words,
            energy_intervals=energy,
            scene_intervals=scenes,
        )
        if options.reframe_mode != "center_crop_9_16":
            warnings.append(
                "reframe_mode is handled by the shorts.reframe step; "
                "shorts.select no longer tracks faces"
            )

        context.selected_shorts = list(selected)
        context.shorts = [
            {
                **clip.to_dict(media.audio_sample_rate),
                "aspect_ratio": options.aspect_ratio,
                "width": width,
                "height": height,
            }
            for clip in selected
        ]
        context.hashes["shorts"] = digest_payload(context.shorts)
        message = (
            f"{len(selected)} shorts selected"
            if selected
            else "No window reached the minimum duration"
        )
        io.emit("info", message, module="shorts")
        io.report(100, message)
