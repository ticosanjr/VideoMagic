"""Human curation previews for music, B-roll, SFX, and a minute sample."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from videoflow.application import hilt
from videoflow.application.curation import curation_manifest
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import HumanInputRequiredError
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class CurationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interactive: bool = False
    gate_id: str = "curation"


@register_step
class CurationPrepareStep(BaseStep):
    type = "curation.prepare"
    title = "Curation previews"
    description = (
        "Build music candidates, a labeled B-roll contact sheet, SFX demo, "
        "and a one-minute sample."
    )
    produces = ("curation",)
    params_model = CurationParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = CurationParams.model_validate(params)
        project_id = str(context.metadata.get("project_id") or "")
        if not project_id:
            io.report(100, "Curation skipped: no project id")
            return
        manifest = curation_manifest(project_id)
        context.metadata["curation"] = manifest
        context.artifacts["curation"] = str(manifest.get("path") or "")
        if options.interactive:
            questions = [
                {
                    "id": "music",
                    "label": "Choose the music bed",
                    "type": "choice",
                    "options": [item["id"] for item in manifest.get("music", [])],
                    "required": True,
                },
                {
                    "id": "broll",
                    "label": "Choose the B-roll direction",
                    "type": "choice",
                    "options": [
                        item["id"] for item in (manifest.get("broll") or {}).get("candidates", [])
                    ],
                    "required": False,
                },
            ]
            request, token = hilt.create_request(
                context.output,
                step_id=io.stage,
                gate_id=options.gate_id,
                kind="review",
                title="Curation previews",
                description="Choose music and B-roll before the full render.",
                questions=questions,
                artifacts=[
                    item["preview"] for item in manifest.get("music", []) if item.get("preview")
                ]
                + [str((manifest.get("broll") or {}).get("contact_sheet") or "")]
                + [str((manifest.get("sample") or {}).get("path") or "")],
                job_id=str(context.metadata.get("job_id") or ""),
            )
            from videoflow.application import hilt_channels

            hilt_channels.notify_request(context.output, request, token)
            response = hilt.load_response(context.output, request.interaction_id)
            if response is None:
                raise HumanInputRequiredError(
                    hilt.public_payload(context.output, request),
                    message="Choose music and B-roll before the full render.",
                )
            context.metadata["curation_choice"] = dict(response.answers)
        io.report(100, "Curation previews ready")


__all__ = ["CurationPrepareStep"]
