"""Apply a minimum transformative treatment to downloaded clips."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.domain.headless import TransformativeRecord
from videoflow.runtime import find_binary
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class TransformativeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[str] = Field(default_factory=list)
    mode: str = Field(default="auto", pattern="^(auto|zoom|crop|frame|overlay)$")
    min_zoom: float = Field(default=1.08, ge=1.0, le=1.5)
    frame: bool = True
    overlay: str = ""
    apply: bool = True


@register_step
class TransformativeGuardStep(BaseStep):
    type = "assets.transformative_guard"
    status = "partial"
    icon = "©"
    color = "#f97316"
    title = "Transformative guard"
    description = "Zoom/crop/frame downloaded clips so they carry transformative treatment."
    requires = ()
    produces = ("transformative_records",)
    params_model = TransformativeParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = TransformativeParams.model_validate(params)
        records: list[TransformativeRecord] = []
        output_dir = context.work / "transformative"
        output_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg = find_binary("ffmpeg")
        for index, raw in enumerate(options.sources):
            source = Path(raw).expanduser()
            if not source.is_file():
                context.warnings.append(f"transformative source missing: {source}")
                continue
            target = output_dir / f"{index:02d}-{source.stem}.mp4"
            note = "plan-only"
            if options.apply and ffmpeg is not None:
                zoom = max(1.0, options.min_zoom)
                width = f"iw/{zoom:.4f}"
                height = f"ih/{zoom:.4f}"
                command = [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-vf",
                    f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2,scale=iw:ih",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-c:a",
                    "copy",
                    str(target),
                ]
                completed = subprocess.run(command, capture_output=True, text=True, check=False)
                if completed.returncode == 0:
                    note = "rendered"
                else:
                    context.warnings.append(
                        f"transformative render failed for {source.name}: "
                        f"{completed.stderr.strip()[-300:]}"
                    )
            records.append(
                TransformativeRecord(
                    source=str(source),
                    output=str(target) if target.is_file() else "",
                    mode=options.mode,
                    zoom=options.min_zoom,
                    crop=[0.0, 0.0, 1.0, 1.0],
                    overlay=options.overlay,
                    note=note,
                )
            )
            io.report(
                int((index + 1) / max(1, len(options.sources)) * 100),
                f"Transformative guard {index + 1}/{len(options.sources)}",
            )
        context.metadata["transformative_records"] = [
            record.model_dump(mode="json") for record in records
        ]
        path = context.work / "transformative.json"
        path.write_text(
            __import__("json").dumps(
                [record.model_dump(mode="json") for record in records], indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        context.artifacts["transformative_records"] = str(path)
        io.report(100, f"{len(records)} transformative record(s)")
