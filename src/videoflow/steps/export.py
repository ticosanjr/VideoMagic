"""NLE export step."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.export_service import export_timeline
from videoflow.application.nle_extras import nle_extras_from_output
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import StateNotReadyError
from videoflow.exporters.fcpxml import Dialect
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class ExportParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[Literal["resolve", "premiere", "kdenlive", "mp4"]] = Field(
        default_factory=lambda: ["resolve", "premiere", "kdenlive"]
    )
    dialect: Dialect = "1.9"
    subdir: str = "exports"


@register_step
class ExportStep(BaseStep):
    type = "export.nle"
    title = "Export timelines"
    description = "Write FCPXML, XMEML, Kdenlive, and/or a direct MP4 from the same timeline."
    requires = ("edit.timeline",)
    produces = ("nle_artifacts",)
    params_model = ExportParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ExportParams.model_validate(params)
        if context.state is None:
            raise StateNotReadyError("The export step requires a built timeline")
        destination = context.output / options.subdir
        destination.mkdir(parents=True, exist_ok=True)
        io.report(20, "Writing NLE timelines")
        completed = 0
        target_count = max(1, len(options.targets))

        def on_progress(target: str, value: int) -> None:
            nonlocal completed
            io.check_cancel()
            local = max(0, min(100, int(value)))
            overall = 20 + int(
                ((completed + local / 100) / target_count) * 75
            )
            io.report(min(95, overall), f"Exporting {target} ({local}%)")
            if local >= 100:
                completed += 1

        adapter = (
            io.adapter
            if getattr(io.adapter, "render", None) is not None
            else FFmpegAdapter(cancel_event=io.cancel_event)
        )
        artifacts = export_timeline(
            context.state,
            destination,
            targets=options.targets,
            dialect=options.dialect,
            extras=nle_extras_from_output(context.output),
            progress=on_progress,
            should_cancel=io.check_cancel,
            adapter=adapter,
            cache_dir=context.output / "render" / "segments",
        )
        context.artifacts.update({name: str(path) for name, path in artifacts.items()})
        sidecars = destination / "sidecars"
        sidecars.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for relative in (
            "titles.ass",
            "titles.json",
            "broll.json",
            "timeline_meta.json",
            "audio/master.wav",
            "audio/master-filters.json",
            "color/filters.json",
        ):
            source = context.output / relative
            if not source.is_file():
                continue
            target = sidecars / Path(relative).name
            shutil.copy2(source, target)
            copied.append(target.name)
        markers: list[object] = []
        meta_path = context.output / "timeline_meta.json"
        if meta_path.is_file():
            try:
                markers = list(
                    json.loads(meta_path.read_text(encoding="utf-8")).get("markers", [])
                )
            except (OSError, ValueError):
                markers = []
        manifest = {
            "ok": True,
            "note": (
                "Native titles, markers, colour filters, B-roll, and the audio "
                "master are in the timeline files. The sidecars remain the "
                "interchange copy for manual review."
            ),
            "files": copied,
            "broll_plan": context.metadata.get("broll_plan", {}),
            "markers": markers,
        }
        (sidecars / "sidecars.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        (sidecars / "README.md").write_text(
            "# NLE sidecars\n\n"
            "The timeline files are the primary edit. These sidecars carry the "
            "looks and graphics that the NLE cannot round-trip from JSON:\n\n"
            "- `titles.ass`: title cards and speaker lower thirds.\n"
            "- `master.wav`: dialogue master reference.\n"
            "- `master-filters.json`: loudness/denoise chain.\n"
            "- `filters.json`: LUT/eq color chain.\n"
            "- `broll.json` and `timeline_meta.json`: B-roll plan and markers.\n",
            encoding="utf-8",
        )
        context.artifacts["sidecars"] = str(sidecars / "sidecars.json")
        context.hashes["export"] = digest_payload(
            {name: str(path) for name, path in artifacts.items()}
        )
        io.report(100, f"{len(artifacts)} NLE artifacts written")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(Path(path) for path in context.artifacts.values())
