"""Reframe selected Shorts with static crop or motion/face tracking."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.crop import crop_box, face_center_focus
from videoflow.application.tracking import track_focus, track_focus_x
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
    tracking_backend: Literal["auto", "opencv_haar", "mediapipe", "yolo"] = "auto"
    smoothing_factor: float = Field(default=0.85, ge=0.0, le=0.99)
    dynamic_crop: bool = False
    layout: Literal["single", "split_screen", "pip"] = "single"
    compute_policy: Literal["auto", "local", "remote", "remote_only"] = "auto"
    allow_slow_cpu_fallback: bool = True


@register_step
class ReframeStep(BaseStep):
    type = "shorts.reframe"
    status = "partial"
    icon = "⛶"
    color = "#f59e0b"

    title = "Reframe Shorts"
    description = (
        "Choose the crop focus for each selected Short, optionally tracking the "
        "active face or motion. Dialogue clips can switch to a two-panel layout."
    )
    requires = ("shorts.select",)
    produces = ("reframed_shorts",)
    params_model = ReframeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ReframeParams.model_validate(params)
        media = require_media(context)
        try:
            from videoflow.application.settings import load_settings

            vision = load_settings().vision
        except Exception:  # noqa: BLE001 - defaults are safe
            vision = None
        if not context.selected_shorts:
            io.report(100, "No Shorts to reframe")
            return

        def with_split(clip, focus: float):
            sentence_ids = set(clip.sentence_ids)
            speakers = {
                sentence.speaker for sentence in context.transcript if sentence.id in sentence_ids
            }
            split = options.layout == "split_screen" or (
                options.layout == "single"
                and options.split_screen_on_dialogue
                and len(speakers) > 1
            )
            return replace(
                clip,
                crop_focus_x=focus,
                split_screen=split,
                split_screen_focus_left=max(0.0, min(1.0, focus - 0.2)),
                split_screen_focus_right=max(0.0, min(1.0, focus + 0.2)),
            )

        sample_rate = media.audio_sample_rate

        def with_static_keyframes(clip, focus: float):
            if clip.crop_keyframes:
                return clip
            duration = clip.duration_samples / sample_rate if sample_rate else 0.0
            return replace(
                clip,
                crop_keyframes=((0.0, focus), (round(duration, 3), focus)),
            )

        if options.mode == "center_crop_9_16":
            for index, clip in enumerate(context.selected_shorts):
                updated = with_static_keyframes(with_split(clip, 0.5), 0.5)
                context.selected_shorts[index] = updated
                if index < len(context.shorts):
                    context.shorts[index]["crop_focus_x"] = 0.5
                    context.shorts[index]["crop_keyframes"] = [
                        [0.0, 0.5],
                        [round(updated.duration_samples / sample_rate, 3), 0.5],
                    ]
                    context.shorts[index]["split_screen"] = updated.split_screen
                    context.shorts[index]["split_screen_focus_left"] = (
                        updated.split_screen_focus_left
                    )
                    context.shorts[index]["split_screen_focus_right"] = (
                        updated.split_screen_focus_right
                    )
            context.hashes["reframe"] = digest_payload(
                {
                    "mode": options.mode,
                    "split": [clip.split_screen for clip in context.selected_shorts],
                }
            )
            io.report(100, "Center crop selected")
            return

        io.report(10, f"Tracking focus with {options.mode}")
        tracked = []
        tracking_report: list[dict[str, object]] = []
        total = max(1, len(context.selected_shorts))
        source_path = Path(context.source)
        settings_args = {
            "yolo_model": getattr(vision, "yolo_model", ""),
            "yolo_confidence": getattr(vision, "yolo_confidence", 0.35),
            "mediapipe_model": getattr(vision, "mediapipe_model", 1),
            "mediapipe_model_path": getattr(vision, "mediapipe_model_path", ""),
        }
        for index, clip in enumerate(context.selected_shorts):
            io.check_cancel()
            entry = context.shorts[index] if index < len(context.shorts) else {}
            aspect = str(entry.get("aspect_ratio") or "9:16")
            target_crop = crop_box(media.width, media.height, aspect=aspect)
            tracking_mode = options.mode
            if options.tracking_backend in {"mediapipe", "yolo", "opencv_haar"}:
                tracking_mode = "face_tracking"
            keyframes: list[dict[str, float]] = []
            if options.dynamic_crop:
                result = track_focus(
                    source_path,
                    clip.pieces,
                    sample_rate,
                    mode=tracking_mode,
                    smoothing=options.smoothing_factor,
                    fps=getattr(vision, "tracking_sample_fps", 2),
                    backend=options.tracking_backend,
                    **settings_args,
                )
                keyframes = result.keyframes
                used_mode = result.backend
                focus = (
                    sum(item["focus_x"] for item in keyframes) / len(keyframes)
                    if keyframes
                    else 0.5
                )
                reason = result.reason
                frames = result.frames
                detections = result.detections
            else:
                focus, used_mode = track_focus_x(
                    source_path,
                    clip.pieces,
                    sample_rate,
                    mode=tracking_mode,
                    backend=options.tracking_backend,
                )
                reason = ""
                frames = detections = 0
            if used_mode in {"opencv_haar", "mediapipe", "yolo", "face_tracking"}:
                # Tracking returns the face center in source coordinates. The
                # crop focus is the offset of that center, not the center itself.
                focus = face_center_focus(
                    focus,
                    source_width=media.width,
                    crop_width=target_crop.width,
                )
                keyframes = [
                    {
                        **item,
                        "focus_x": face_center_focus(
                            item["focus_x"],
                            source_width=media.width,
                            crop_width=target_crop.width,
                        ),
                    }
                    for item in keyframes
                ]
            requested = options.tracking_backend
            if requested != "auto" and used_mode != requested:
                context.warnings.append(f"{requested} unavailable; used {used_mode}")
            elif used_mode == "motion_tracking" and options.mode == "face_tracking":
                context.warnings.append(f"{options.mode} unavailable; used {used_mode}")
            tracking_report.append(
                {
                    "clip_id": getattr(clip, "clip_id", f"short-{index + 1}"),
                    "requested": requested,
                    "backend": used_mode,
                    "reason": reason,
                    "frames": frames,
                    "detections": detections,
                    "keyframes": len(keyframes),
                    "face_center_lock": used_mode
                    in {"opencv_haar", "mediapipe", "yolo", "face_tracking"},
                }
            )
            updated = with_split(clip, focus)
            if keyframes:
                updated = replace(
                    updated,
                    crop_keyframes=tuple((item["time_sec"], item["focus_x"]) for item in keyframes),
                )
            else:
                updated = with_static_keyframes(updated, focus)
            tracked.append(updated)
            if index < len(context.shorts):
                context.shorts[index]["crop_focus_x"] = round(focus, 4)
                context.shorts[index]["tracking_backend_used"] = used_mode
                context.shorts[index]["crop_keyframes"] = (
                    [[item["time_sec"], item["focus_x"]] for item in keyframes]
                    if keyframes
                    else [
                        [0.0, round(focus, 4)],
                        [round(updated.duration_samples / sample_rate, 3), round(focus, 4)],
                    ]
                )
                context.shorts[index]["split_screen"] = updated.split_screen
                context.shorts[index]["split_screen_focus_left"] = updated.split_screen_focus_left
                context.shorts[index]["split_screen_focus_right"] = updated.split_screen_focus_right
            io.report(int((index + 1) / total * 100), f"Reframed {index + 1}/{total}")
        context.selected_shorts = tracked
        report_path = context.output / "vision" / "tracking.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {"backend": options.tracking_backend, "clips": tracking_report},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        context.metadata["tracking"] = tracking_report
        context.artifacts["tracking"] = str(report_path)
        context.hashes["reframe"] = digest_payload(
            {"mode": options.mode, "focus": [clip.crop_focus_x for clip in tracked]}
        )
        io.report(100, f"{len(tracked)} Shorts reframed")
