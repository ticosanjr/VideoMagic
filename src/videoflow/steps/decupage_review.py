"""Deterministic prefilter, LLM window contract, and decision application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.decupage.llm import (
    apply_decisions,
    audit_prompt,
    build_windows,
    parse_audit,
    parse_decisions,
    pass1_prompt,
)
from videoflow.application.decupage.prefilter import prefilter
from videoflow.core.context import PipelineContext
from videoflow.domain.decupage import Asu, AsuDecision
from videoflow.domain.errors import CapabilityUnavailableError, StateNotReadyError
from videoflow.domain.paths import resolve_allowed
from videoflow.runtime import allowed_roots
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step


def _asus(context: PipelineContext) -> list[Asu]:
    raw = context.metadata.get("asus")
    if not isinstance(raw, list) or not raw:
        raise StateNotReadyError("Run speech.asu before decupage review")
    result: list[Asu] = []
    for item in raw:
        try:
            result.append(Asu.model_validate(item))
        except (TypeError, ValueError):
            continue
    if not result:
        raise StateNotReadyError("No valid ASUs are available")
    return result


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


class PrefilterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lookahead_seconds: float = Field(default=45.0, ge=1.0, le=300.0)
    min_words: int = Field(default=3, ge=1, le=20)
    prefix_similarity: float = Field(default=0.78, ge=0.0, le=1.0)
    token_similarity: float = Field(default=0.72, ge=0.0, le=1.0)
    max_group_seconds: float = Field(default=180.0, ge=15.0, le=600.0)


@register_step
class DecupagePrefilterStep(BaseStep):
    type = "decupage.prefilter"
    title = "Decupage prefilter"
    description = "Group fuzzy retakes and quarantine isolated noise before the LLM pass."
    requires = ("speech.asu",)
    produces = ("asus", "decupage_prefilter")
    params_model = PrefilterParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = PrefilterParams.model_validate(params)
        asus = _asus(context)
        result = prefilter(
            asus,
            lookahead_seconds=options.lookahead_seconds,
            min_words=options.min_words,
            prefix_similarity=options.prefix_similarity,
            token_similarity=options.token_similarity,
            max_group_seconds=options.max_group_seconds,
        )
        payload = {
            "report": result.report,
            "asus": [item.model_dump(mode="json") for item in result.asus],
            "decisions": [item.model_dump(mode="json") for item in result.decisions],
        }
        target = context.work / "decupage" / "prefilter.json"
        _write_json(target, payload)
        context.metadata["asus"] = payload["asus"]
        context.metadata["decupage_prefilter"] = result.report
        context.metadata["decupage_prefilter_decisions"] = payload["decisions"]
        context.artifacts["decupage_prefilter"] = str(target)
        context.hashes["decupage.prefilter"] = digest_payload(payload)
        io.report(
            100,
            f"{result.report['groups']} retake group(s), "
            f"{result.report['noise']} noise decision(s)",
        )


class LlmParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["pass1", "audit"] = "pass1"
    llm_policy: Literal["caller", "videoflow", "none"] = "caller"
    provider_id: str = ""
    window_sec: float = Field(default=240.0, ge=30.0, le=600.0)
    overlap_sec: float = Field(default=45.0, ge=0.0, le=180.0)
    max_words: int = Field(default=600, ge=50, le=4000)
    max_discard_ratio: float = Field(default=0.45, ge=0.05, le=0.9)
    max_keep_chars: int = Field(default=12_000, ge=1000, le=100_000)


@register_step
class DecupageLlmStep(BaseStep):
    type = "decupage.llm"
    title = "Decupage LLM"
    description = (
        "Prepare or run the semantic review over ASU IDs. In caller mode it "
        "writes an explicit llm_request and never calls a model."
    )
    requires = ("speech.asu",)
    produces = ("decupage_llm", "decupage_decisions")
    params_model = LlmParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = LlmParams.model_validate(params)
        asus = _asus(context)
        windows = build_windows(
            asus,
            window_sec=options.window_sec,
            overlap_sec=options.overlap_sec,
            max_words=options.max_words,
        )
        role = (
            "decupage.semantic_pass1"
            if options.mode == "pass1"
            else "decupage.continuity_audit"
        )
        contract: dict[str, Any] = {
            "required": options.llm_policy != "none",
            "policy": options.llm_policy,
            "mode": options.mode,
            "roles": [
                {
                    "role": role,
                    "required": options.llm_policy != "none",
                    "status": "waiting" if options.llm_policy == "caller" else "pending",
                }
            ],
            "status": "waiting" if options.llm_policy == "caller" else "pending",
            "calls_planned": len(windows) if options.mode == "pass1" else 1,
            "calls_made": 0,
        }
        context.metadata["decupage_llm"] = contract
        if options.llm_policy == "none":
            contract["status"] = "skipped"
            contract["roles"][0]["status"] = "skipped"
            _write_json(context.work / "decupage" / "llm_contract.json", contract)
            context.artifacts["decupage_llm_contract"] = str(
                context.work / "decupage" / "llm_contract.json"
            )
            io.report(100, "LLM review skipped by llm_policy=none")
            return

        if options.mode == "audit":
            decisions = [
                AsuDecision.model_validate(item)
                for item in context.metadata.get("decupage_decisions", [])
                if isinstance(item, dict)
            ]
            removed = {
                decision.asu_id
                for decision in decisions
                if decision.action == "REMOVE"
            }
            request = {
                "schema": "decupage_audit_v1",
                "instructions": "Return restore_asu_ids only for orphaned or duplicated KEEP ASUs.",
                "asus": [
                    {"asu_id": item.asu_id, "text": item.text}
                    for item in asus
                    if item.asu_id not in removed
                ][:2000],
                "removed_candidates": [
                    {"asu_id": item.asu_id, "text": item.text}
                    for item in asus
                    if item.asu_id in removed
                ][:2000],
            }
            prompt = audit_prompt(asus, decisions)
            allowed = {item.asu_id for item in asus}
        else:
            request = {
                "schema": "decupage_decisions_v1",
                "instructions": (
                    "Use only asu_id and word indexes. Never generate timestamps. "
                    "Last-take-wins; keep intentional rhetoric; KEEP when unsure."
                ),
                "prefilter_decisions": context.metadata.get(
                    "decupage_prefilter_decisions", []
                ),
                "windows": [item.model_dump(mode="json") for item in windows],
            }
            prompt = ""

        if options.llm_policy == "caller":
            target = context.work / "decupage" / f"llm_request_{options.mode}.json"
            _write_json(target, request)
            contract["status"] = "waiting"
            context.metadata["decupage_llm"] = contract
            context.artifacts["decupage_llm_request"] = str(target)
            _write_json(context.work / "decupage" / "llm_contract.json", contract)
            context.artifacts["decupage_llm_contract"] = str(
                context.work / "decupage" / "llm_contract.json"
            )
            io.report(
                100,
                "LLM review required; request written. Submit decisions with decupage.apply.",
            )
            return

        client = io.llm_client
        if client is None:
            raise CapabilityUnavailableError(
                "llm",
                "Configure an LLM provider or use llm_policy=caller.",
            )
        calls = 0
        decisions: list[AsuDecision] = []
        try:
            if options.mode == "audit":
                raw = client.complete_json(prompt, "videoflow.decupage_audit")
                calls = 1
                decisions = parse_audit(raw, allowed)
            else:
                by_id = {item.asu_id: item for item in asus}
                for window in windows:
                    raw = client.complete_json(
                        pass1_prompt(window), "videoflow.decupage_pass1"
                    )
                    calls += 1
                    decisions.extend(
                        parse_decisions(
                            raw,
                            allowed=set(window.asu_ids),
                            asus=by_id,
                        )
                    )
        except Exception as exc:  # noqa: BLE001 - LLM boundary must be explicit
            contract.update(status="failed", calls_made=calls, error=str(exc))
            contract["roles"][0]["status"] = "failed"
            context.metadata["decupage_llm"] = contract
            contract_path = context.work / "decupage" / "llm_contract.json"
            _write_json(contract_path, contract)
            context.artifacts["decupage_llm_contract"] = str(contract_path)
            raise

        contract.update(status="done", calls_made=calls)
        contract["roles"][0]["status"] = "done"
        context.metadata["decupage_llm"] = contract
        contract_path = context.work / "decupage" / "llm_contract.json"
        _write_json(contract_path, contract)
        context.artifacts["decupage_llm_contract"] = str(contract_path)
        stored = (
            list(context.metadata.get("decupage_decisions", []))
            if options.mode == "audit"
            else []
        )
        payload = {
            "mode": options.mode,
            "contract": contract,
            "decisions": [
                *stored,
                *[item.model_dump(mode="json") for item in decisions],
            ],
        }
        target = context.work / "decupage" / f"llm_result_{options.mode}.json"
        _write_json(target, payload)
        context.metadata["decupage_decisions"] = payload["decisions"]
        context.artifacts["decupage_decisions"] = str(target)
        context.artifacts["decupage_llm_contract"] = str(
            context.work / "decupage" / "llm_contract.json"
        )
        context.hashes["decupage.llm"] = digest_payload(payload)
        io.report(100, f"{len(decisions)} LLM decision(s) in {calls} call(s)")


class ApplyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[dict[str, Any]] | None = None
    decisions_path: str = ""
    max_discard_ratio: float = Field(default=0.45, ge=0.05, le=0.9)


@register_step
class DecupageApplyStep(BaseStep):
    type = "decupage.apply"
    title = "Apply decupage decisions"
    description = "Validate LLM decisions and write ASU cuts, review flags, and state."
    requires = ("speech.asu",)
    produces = ("decupage_state",)
    params_model = ApplyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ApplyParams.model_validate(params)
        asus = _asus(context)
        raw_decisions: list[Any] = list(
            context.metadata.get("decupage_prefilter_decisions", [])
        )
        raw_decisions.extend(context.metadata.get("decupage_decisions", []))
        if options.decisions is not None:
            raw_decisions.extend(options.decisions)
        elif options.decisions_path:
            path = resolve_allowed(Path(options.decisions_path), allowed_roots())
            if not path.is_file():
                raise StateNotReadyError(f"Decisions file not found: {path}")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                raw_decisions.extend(payload.get("decisions") or [])
                raw_decisions.extend(
                    {"asu_id": item, "action": "RESTORE", "category": "CONTINUITY"}
                    for item in payload.get("restore_asu_ids", [])
                )
            elif isinstance(payload, list):
                raw_decisions.extend(payload)
        else:
            raw_decisions.extend(context.metadata.get("decupage_decisions", []))

        decisions: list[AsuDecision] = []
        for item in raw_decisions:
            try:
                decisions.append(AsuDecision.model_validate(item))
            except (TypeError, ValueError):
                continue
        updated, cuts, flags, summary = apply_decisions(
            asus,
            decisions,
            max_discard_ratio=options.max_discard_ratio,
        )
        payload = {
            "asus": [item.model_dump(mode="json") for item in updated],
            "cuts": cuts,
            "review_flags": flags,
            "summary": summary,
            "decisions": [item.model_dump(mode="json") for item in decisions],
        }
        target = context.work / "decupage" / "state.json"
        _write_json(target, payload)
        context.metadata["asus"] = payload["asus"]
        context.metadata["decupage_cuts"] = cuts
        context.metadata["decupage_review_flags"] = flags
        context.metadata["decupage_state"] = summary
        context.artifacts["decupage_state"] = str(target)
        context.hashes["decupage.apply"] = digest_payload(payload)
        io.report(
            100,
            f"{summary['removed']} removed, {summary['trimmed']} trimmed, "
            f"{summary['review_flags']} review flag(s)",
        )
