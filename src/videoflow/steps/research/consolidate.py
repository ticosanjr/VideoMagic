"""Research consolidation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step
from videoflow.steps.research.params import ConsolidateParams
from videoflow.steps.research.prompts import CONSOLIDATE_PROMPT
from videoflow.steps.research.support import (
    _normalize_case,
    _read_agent_payloads,
    _render_research_markdown,
    _write_json,
    _write_text,
)


@register_step
class ConsolidateStep(BaseStep):
    type = "research.consolidate"
    title = "Consolidate research"
    description = (
        "Merge the scoped dossiers, drop duplicate cases, preserve unique facts, "
        "and write one master research document."
    )
    status = "available"
    icon = "⇉"
    color = "#a78bfa"
    params_model = ConsolidateParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ConsolidateParams.model_validate(params)
        payloads = _read_agent_payloads(context)
        merged: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for payload in payloads:
            for raw in payload.get("cases", []):
                if not isinstance(raw, dict):
                    continue
                key = re.sub(r"\s+", " ", str(raw.get("title") or "untitled")).strip().casefold()
                existing = merged.get(key)
                if existing is None:
                    merged[key] = {
                        "title": str(raw.get("title") or "Untitled case"),
                        "summary": str(raw.get("summary") or ""),
                        "defense": str(raw.get("defense") or ""),
                        "published_at": str(raw.get("published_at") or ""),
                        "sources": list(raw.get("sources") or []),
                    }
                    continue
                if len(str(raw.get("summary") or "")) > len(existing["summary"]):
                    existing["summary"] = str(raw.get("summary") or "")
                if not existing.get("defense") and raw.get("defense"):
                    existing["defense"] = str(raw["defense"])
                known = {item.get("url") for item in existing["sources"]}
                for source in raw.get("sources") or []:
                    if isinstance(source, dict) and source.get("url") not in known:
                        existing["sources"].append(source)
                        known.add(source.get("url"))
        cases = list(merged.values())[: options.max_cases]
        notes = ""
        generated_by = "deterministic"
        if io.llm_client is not None and cases:
            prompt = CONSOLIDATE_PROMPT.format(cases=json.dumps(cases, ensure_ascii=False)[:30000])
            try:
                payload = io.llm_client.complete_json(prompt, "videoflow.research.master")
                raw_cases = payload.get("cases") if isinstance(payload, dict) else []
                if isinstance(raw_cases, list) and raw_cases:
                    allowed = {
                        str(source.get("url"))
                        for case in cases
                        for source in case.get("sources", [])
                        if isinstance(source, dict)
                    }
                    cases = [
                        _normalize_case(item, allowed)
                        for item in raw_cases[: options.max_cases]
                        if isinstance(item, dict)
                    ]
                    notes = str(payload.get("notes") or "")
                    generated_by = "llm"
            except Exception as exc:  # noqa: BLE001 - deterministic merge is still valid
                warnings.append(f"Consolidation model fallback: {exc}")
        if options.require_sources:
            missing = [
                case["title"]
                for case in cases
                if not any(source.get("url") for source in case.get("sources", []))
            ]
            if missing:
                warnings.append(f"{len(missing)} case(s) have no source and need human review.")
        master = {
            "topic": payloads[0].get("topic", "") if payloads else "",
            "agent_count": len(payloads),
            "case_count": len(cases),
            "cases": cases,
            "notes": notes,
            "generated_by": generated_by,
            "warnings": warnings,
            "sources": [
                source
                for case in cases
                for source in case.get("sources", [])
                if isinstance(source, dict)
            ],
        }
        _write_json(context.output / "research" / "master.json", master)
        _write_text(
            context.output / "research" / "master.md",
            _render_research_markdown(
                "Master research",
                str(master.get("topic") or ""),
                cases,
                notes or " | ".join(warnings),
            ),
        )
        context.metadata["research_master"] = master
        context.artifacts["research_master"] = str(context.output / "research" / "master.md")
        context.artifacts["research_master_json"] = str(context.output / "research" / "master.json")
        context.hashes["research.consolidate"] = digest_payload(
            {"cases": len(cases), "agents": len(payloads)}
        )
        io.report(100, f"{len(cases)} case(s) consolidated")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return (
            Path(context.artifacts["research_master"]),
            Path(context.artifacts["research_master_json"]),
        )
