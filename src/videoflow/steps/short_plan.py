"""Plan a dynamic vertical Short from the scene supercontext."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.scene_intel.io import read_json, write_json
from videoflow.application.short_composition.io import read_manifest, read_supercontext
from videoflow.application.short_composition.plan import resolve_draft
from videoflow.application.short_composition.planner import (
    build_llm_request,
    default_window,
    deterministic_draft,
    parse_llm_response,
    plan_prompt,
)
from videoflow.application.short_composition.validate import validate_plan
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import CapabilityUnavailableError, ShortPlanError, StateNotReadyError
from videoflow.domain.scenes import ScenesManifest
from videoflow.domain.short_composition import ShortCompositionDraft
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


class ShortPlanParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    short_id: str = "SH_001"
    start_sec: float = Field(default=0.0, ge=0.0)
    end_sec: float = Field(default=0.0, ge=0.0)
    max_sec: float = Field(default=60.0, ge=3.0, le=180.0)
    llm_policy: Literal["caller", "videoflow", "none"] = "caller"
    llm_role: str = "shorts.composition"
    provider_id: str = ""
    min_segment_sec: float = Field(default=2.5, ge=1.0, le=10.0)
    max_upscale: float = Field(default=2.5, ge=1.0, le=5.0)
    smooth_track: bool = False
    strict: bool = True
    plan: dict[str, Any] | None = None
    plan_path: str = ""


def _manifest(context: PipelineContext) -> ScenesManifest:
    return read_manifest(
        context,
        step="short.plan",
        error_cls=StateNotReadyError,
        error_prefix="Scene manifest is invalid",
    )


def _supercontext(context: PipelineContext) -> dict[str, Any]:
    return read_supercontext(context)


def _submitted_plan(
    options: ShortPlanParams,
    *,
    start: float,
    end: float,
    topology: str,
) -> ShortCompositionDraft | None:
    payload: dict[str, Any] = {}
    if options.plan_path:
        payload = read_json(Path(options.plan_path).expanduser())
        if not payload:
            raise ShortPlanError(
                f"Short plan file is missing or invalid: {options.plan_path}"
            )
    if options.plan:
        payload = dict(options.plan)
    if not payload:
        return None
    if "start" in payload and "end" in payload:
        try:
            return ShortCompositionDraft.model_validate(payload)
        except ValueError as exc:
            raise ShortPlanError(f"Invalid Short plan: {exc}") from exc
    return parse_llm_response(
        payload,
        short_id=options.short_id,
        start_sec=start,
        end_sec=end,
        source_topology=topology,
    )


@register_step
class ShortPlanStep(BaseStep):
    type = "short.plan"
    title = "Plan dynamic Short"
    description = (
        "Resolve scene anchors into a contiguous 1080x1920 plan, with explicit "
        "LLM caller/videoflow/none policies and deterministic fallback."
    )
    status = "available"
    icon = "▭"
    color = "#8b5cf6"
    requires = ("scene.analyze",)
    produces = ("short_plan", "short_plan_report")
    params_model = ShortPlanParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ShortPlanParams.model_validate(params)
        manifest = _manifest(context)
        start, end = default_window(
            manifest,
            start_sec=options.start_sec,
            end_sec=options.end_sec,
            max_sec=options.max_sec,
        )
        workspace = Path(context.output) / "shorts" / options.short_id
        request = build_llm_request(
            _supercontext(context),
            short_id=options.short_id,
            start_sec=start,
            end_sec=end,
            min_segment_sec=options.min_segment_sec,
        )
        contract: dict[str, Any] = {
            "required": options.llm_policy != "none",
            "policy": options.llm_policy,
            "role": options.llm_role,
            "provider_id": options.provider_id,
            "status": "pending",
            "calls_planned": 1 if options.llm_policy != "none" else 0,
            "calls_made": 0,
        }
        draft = _submitted_plan(
            options,
            start=start,
            end=end,
            topology=manifest.source_topology,
        )
        if draft is not None:
            contract["status"] = "provided"
            contract["calls_made"] = 0
        elif options.llm_policy == "none":
            draft = deterministic_draft(
                manifest,
                short_id=options.short_id,
                start_sec=start,
                end_sec=end,
                max_sec=options.max_sec,
            )
            contract["status"] = "skipped"
        elif options.llm_policy == "caller":
            target = context.work / "shorts" / options.short_id / "llm_request.json"
            write_json(target, request)
            contract["status"] = "waiting"
            context.metadata["short_plan_llm"] = contract
            context.artifacts["short_plan_request"] = str(target)
            context.warnings.append(
                "Short composition requires the calling model; "
                "submit plan=... or plan_path=... to short.plan."
            )
            io.report(100, "Short plan request written")
            return
        else:
            client = io.llm_client
            if client is None:
                raise CapabilityUnavailableError(
                    "llm", "Configure an LLM provider or use llm_policy=caller."
                )
            raw = client.complete_json(plan_prompt(request), options.llm_role)
            if not isinstance(raw, dict):
                raise ShortPlanError("LLM Short plan must be a JSON object")
            draft = parse_llm_response(
                raw,
                short_id=options.short_id,
                start_sec=start,
                end_sec=end,
                source_topology=manifest.source_topology,
            )
            contract["calls_made"] = 1
            contract["status"] = "succeeded"
        assert draft is not None
        result = resolve_draft(
            draft,
            manifest,
            min_segment_sec=options.min_segment_sec,
            smooth_track=options.smooth_track,
            max_upscale=options.max_upscale,
        )
        validation = validate_plan(result.plan, manifest)
        if validation["errors"] and options.strict:
            raise ShortPlanError("; ".join(str(item) for item in validation["errors"]))
        for warning in result.warnings + list(validation["warnings"]):
            if warning not in context.warnings:
                context.warnings.append(warning)
        plan_path = workspace / "short_composition_plan.json"
        report_path = workspace / "short_plan_report.json"
        write_json(plan_path, result.plan.model_dump(mode="json"))
        report = {
            **result.report,
            "warnings": result.warnings,
            "validation": validation,
            "llm": contract,
            "window": {"start_sec": start, "end_sec": end},
            "smooth_track": options.smooth_track,
        }
        write_json(report_path, report)
        context.metadata["short_plan"] = result.plan.model_dump(mode="json")
        context.metadata["short_plan_report"] = report
        context.metadata["short_plan_llm"] = contract
        context.artifacts["short_plan"] = str(plan_path)
        context.artifacts["short_plan_report"] = str(report_path)
        context.hashes["short.plan"] = digest_payload(
            {"plan": result.plan.model_dump(mode="json"), "report": report}
        )
        io.report(100, f"{len(result.plan.segments)} segment(s) planned")


__all__ = ["ShortPlanParams", "ShortPlanStep"]
