"""Reframe selected Shorts with static crop or motion/face tracking."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from videoflow.application.tracking import track_focus_x
from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload, require_media
from videoflow.steps.registry import register_step

ReframeMode = Literal[
    "center_crop_9_16",
    "motion_tracking",
    "face_tracking",
    "auto_face_tracking_yolo",
]


class ReframeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ReframeMode = "center_crop_9_16"
    split_screen_on_dialogue: bool = False


@register_step
class ReframeStep(BaseStep):
    type = "shorts.reframe"
    title = "Reframe Shorts"
    description = (
        "Choose the crop focus for each selected Short, optionally tracking the "
        "active face or motion. Split-screen is reserved for a later pass."
    )
    requires = ("shorts.select",)
    produces = ("reframed_shorts",)
    params_model = ReframeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ReframeParams.model_validate(params)
        media = require_media(context)
        if not context.selected_shorts:
            io.report(100, "No Shorts to reframe")
            return
        if options.mode == "center_crop_9_16":
            for index, clip in enumerate(context.selected_shorts):
                context.selected_shorts[index] = replace(clip, crop_focus_x=0.5)
                if index < len(context.shorts):
                    context.shorts[index]["crop_focus_x"] = 0.5
            context.hashes["reframe"] = digest_payload({"mode": options.mode})
            io.report(100, "Center crop selected")
            return

        io.report(10, f"Tracking focus with {options.mode}")
        tracked = []
        total = max(1, len(context.selected_shorts))
        for index, clip in enumerate(context.selected_shorts):
            io.check_cancel()
            focus, used_mode = track_focus_x(
                Path(context.source),
                clip.pieces,
                media.audio_sample_rate,
                mode=options.mode,
            )
            if used_mode != options.mode:
                context.warnings.append(
                    f"{options.mode} unavailable; used {used_mode}"
                )
            updated = replace(clip, crop_focus_x=focus)
            tracked.append(updated)
            if index < len(context.shorts):
                context.shorts[index]["crop_focus_x"] = round(focus, 4)
            io.report(int((index + 1) / total * 100), f"Reframed {index + 1}/{total}")
        context.selected_shorts = tracked
        context.hashes["reframe"] = digest_payload(
            {"mode": options.mode, "focus": [clip.crop_focus_x for clip in tracked]}
        )
        io.report(100, f"{len(tracked)} Shorts reframed")
