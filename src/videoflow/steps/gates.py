"""Human-in-the-loop steps: approval, questions, and file handoff."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application import hilt, hilt_channels
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import (
    ApprovalRequiredError,
    HumanInputRequiredError,
    RecipeError,
)
from videoflow.domain.hilt import HiltFileRequest, HiltQuestion
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class _HumanStep(BaseStep):
    status = "available"
    icon = "◇"
    color = "#f59e0b"

    def is_cacheable(self, params: BaseModel) -> bool:
        return False

    @staticmethod
    def _job_id(context: PipelineContext) -> str:
        return str(context.metadata.get("job_id") or "")

    @staticmethod
    def _recipe_id(context: PipelineContext) -> str:
        return str(context.metadata.get("recipe_id") or "")

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        hilt.write_json_atomic(path, payload)


class GateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(default="review", min_length=1, max_length=80)
    title: str = "Review"
    description: str = ""
    summary: str = Field(default="", max_length=4000)
    checklist: list[str] = Field(default_factory=list, max_length=50)
    severity: Literal["info", "warning", "critical"] = "info"
    next_step: str = Field(default="", max_length=1000)
    group: str = Field(default="", max_length=120)
    approve_label: str = "Approve"
    reject_label: str = "Reject"
    artifacts: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    expires_hours: int = Field(default=168, ge=1, le=24 * 365)


@register_step
class HumanGateStep(_HumanStep):
    type = "human.gate"
    title = "Human gate"
    description = "Pause the recipe until a human approves or rejects the current result."
    params_model = GateParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = GateParams.model_validate(params)
        legacy = context.output / "approvals" / f"{options.gate_id}.json"
        if legacy.is_file():
            self._consume_legacy(context, legacy, options, io)
            return
        artifacts = hilt.build_artifacts(context.output, options.artifacts)
        request, token = hilt.create_request(
            context.output,
            step_id=io.stage,
            gate_id=options.gate_id,
            kind="approval",
            title=options.title,
            description=options.description or f"Approve {options.title} to continue.",
            summary=options.summary,
            checklist=options.checklist,
            severity=options.severity,
            next_step=options.next_step,
            group=options.group,
            artifacts=artifacts,
            channels=options.channels,
            expires_hours=options.expires_hours,
            approve_label=options.approve_label,
            reject_label=options.reject_label,
            job_id=self._job_id(context),
            recipe_id=self._recipe_id(context),
        )
        hilt_channels.notify_request(context.output, request, token)
        response = hilt.load_response(context.output, request.interaction_id)
        if response is None:
            raise ApprovalRequiredError(
                options.gate_id,
                options.title,
                options.description or f"Approve {options.title} to continue.",
                step_id=io.stage,
                interaction=hilt.public_payload(context.output, request),
            )
        if response.action == "reject":
            raise RecipeError(
                f"Gate {options.gate_id!r} was rejected"
                + (f": {response.comment}" if response.comment else "")
            )
        context.metadata[f"gate_{options.gate_id}"] = {
            "approved": True,
            "comment": response.comment,
            "interaction_id": request.interaction_id,
            "responded_by": response.responder,
            "response_channel": response.response_channel,
            "attachments": [item.model_dump(mode="json") for item in response.attachments],
        }
        io.report(100, f"Gate {options.gate_id} approved")

    @staticmethod
    def _consume_legacy(
        context: PipelineContext,
        path: Path,
        options: GateParams,
        io: StepIO,
    ) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RecipeError(f"Approval file is invalid: {path}") from exc
        if not payload.get("approved"):
            raise RecipeError(
                f"Gate {options.gate_id!r} was rejected"
                + (f": {payload.get('comment')}" if payload.get("comment") else "")
            )
        context.metadata[f"gate_{options.gate_id}"] = payload
        io.report(100, f"Gate {options.gate_id} approved")


class HumanInputParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(default="input", min_length=1, max_length=80)
    title: str = "Input needed"
    description: str = ""
    summary: str = Field(default="", max_length=4000)
    checklist: list[str] = Field(default_factory=list, max_length=50)
    severity: Literal["info", "warning", "critical"] = "info"
    next_step: str = Field(default="", max_length=1000)
    group: str = Field(default="", max_length=120)
    questions: list[HiltQuestion] = Field(min_length=1, max_length=50)
    channels: list[str] = Field(default_factory=list)
    expires_hours: int = Field(default=168, ge=1, le=24 * 365)
    save_as: str = Field(default="", max_length=1000)


@register_step
class HumanInputStep(_HumanStep):
    type = "human.input"
    title = "Ask a human"
    description = "Pause the recipe and collect typed answers from a person."
    params_model = HumanInputParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = HumanInputParams.model_validate(params)
        request, token = hilt.create_request(
            context.output,
            step_id=io.stage,
            gate_id=options.gate_id,
            kind="question",
            title=options.title,
            description=options.description or "Answer the questions to continue.",
            summary=options.summary,
            checklist=options.checklist,
            severity=options.severity,
            next_step=options.next_step,
            group=options.group,
            questions=options.questions,
            channels=options.channels,
            expires_hours=options.expires_hours,
            job_id=self._job_id(context),
            recipe_id=self._recipe_id(context),
        )
        hilt_channels.notify_request(context.output, request, token)
        response = hilt.load_response(context.output, request.interaction_id)
        if response is None:
            raise HumanInputRequiredError(
                hilt.public_payload(context.output, request),
                message=options.description or "Answer the questions to continue.",
            )
        if response.action == "reject":
            raise RecipeError(
                f"Human input {options.gate_id!r} was rejected"
                + (f": {response.comment}" if response.comment else "")
            )
        payload = {
            "interaction_id": request.interaction_id,
            "answers": dict(response.answers),
            "comment": response.comment,
            "responder": response.responder,
            "channel": response.response_channel,
            "received_at": response.received_at,
        }
        context.metadata["hilt_answers"] = payload
        context.metadata.setdefault("hilt", {})[request.interaction_id] = payload
        target = (
            hilt.resolve_output_path(context.output, options.save_as)
            if options.save_as.strip()
            else context.output / "hilt" / request.interaction_id / "answers.json"
        )
        self._write_json(target, payload)
        context.artifacts[f"hilt_{options.gate_id}"] = str(target)
        io.report(100, f"{len(response.answers)} answer(s) received")


class HumanFilesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str = Field(default="files", min_length=1, max_length=80)
    title: str = "Files needed"
    description: str = ""
    summary: str = Field(default="", max_length=4000)
    checklist: list[str] = Field(default_factory=list, max_length=50)
    severity: Literal["info", "warning", "critical"] = "info"
    next_step: str = Field(default="", max_length=1000)
    group: str = Field(default="", max_length=120)
    files: list[HiltFileRequest] = Field(min_length=1, max_length=50)
    channels: list[str] = Field(default_factory=list)
    expires_hours: int = Field(default=168, ge=1, le=24 * 365)


@register_step
class HumanFilesStep(_HumanStep):
    type = "human.files"
    title = "Request files"
    description = "Pause the recipe and receive new or revised files from a person."
    params_model = HumanFilesParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = HumanFilesParams.model_validate(params)
        request, token = hilt.create_request(
            context.output,
            step_id=io.stage,
            gate_id=options.gate_id,
            kind="files",
            title=options.title,
            description=options.description or "Upload the requested files to continue.",
            summary=options.summary,
            checklist=options.checklist,
            severity=options.severity,
            next_step=options.next_step,
            group=options.group,
            files=options.files,
            channels=options.channels,
            expires_hours=options.expires_hours,
            job_id=self._job_id(context),
            recipe_id=self._recipe_id(context),
        )
        hilt_channels.notify_request(context.output, request, token)
        response = hilt.load_response(context.output, request.interaction_id)
        if response is None:
            raise HumanInputRequiredError(
                hilt.public_payload(context.output, request),
                message=options.description or "Upload the requested files to continue.",
            )
        if response.action == "reject":
            raise RecipeError(
                f"File handoff {options.gate_id!r} was rejected"
                + (f": {response.comment}" if response.comment else "")
            )
        missing = hilt.unresolved_files(request, response)
        if missing:
            raise RecipeError(
                "The following requested files are missing: " + ", ".join(missing)
            )
        manifest = hilt.apply_attachments(context.output, request, response)
        payload = {
            "interaction_id": request.interaction_id,
            "files": manifest,
            "comment": response.comment,
            "responder": response.responder,
            "channel": response.response_channel,
            "received_at": response.received_at,
        }
        context.metadata["hilt_files"] = payload
        context.metadata.setdefault("hilt", {})[request.interaction_id] = payload
        target = context.output / "hilt" / request.interaction_id / "files.json"
        self._write_json(target, payload)
        context.artifacts[f"hilt_{options.gate_id}"] = str(target)
        io.report(100, f"{len(manifest)} file(s) received")
