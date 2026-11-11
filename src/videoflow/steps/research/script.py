"""Dual narration and edition script generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step
from videoflow.steps.research.params import ScriptParams
from videoflow.steps.research.prompts import SCRIPT_PROMPT
from videoflow.steps.research.support import (
    _fallback_script,
    _read_master,
    _render_script,
    _write_json,
    _write_text,
)


@register_step
class DualScriptStep(BaseStep):
    type = "script.dual_output"
    title = "Dual script"
    description = (
        "Turn the master research into a narration script for the studio and an "
        "edition script with visual instructions for every section."
    )
    status = "available"
    icon = "✎"
    color = "#a78bfa"
    params_model = ScriptParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = ScriptParams.model_validate(params)
        cases, topic = _read_master(context)
        answers = context.metadata.get("hilt_answers", {})
        answer_map = answers.get("answers", {}) if isinstance(answers, dict) else {}
        presenter = (
            options.presenter_profile
            or str(answer_map.get("presenter_profile") or "")
        )
        if not presenter:
            profile_path = context.output / "research" / "presenter-profile.md"
            if profile_path.is_file():
                presenter = profile_path.read_text(encoding="utf-8")[:4000]
        sections: list[dict[str, Any]] = []
        notes = ""
        generated_by = "fallback"
        warnings: list[str] = []
        if io.llm_client is not None and cases:
            chunk = max(1, options.max_cases_per_call)
            batches = max(1, (len(cases) + chunk - 1) // chunk)
            batch_words = max(150, options.target_words // batches)
            for start in range(0, len(cases), chunk):
                batch = cases[start : start + chunk]
                prompt = SCRIPT_PROMPT.format(
                    target_words=batch_words,
                    max_sections=options.max_sections,
                    presenter=presenter or "neutral documentary presenter",
                    cases=json.dumps(batch, ensure_ascii=False)[:24000],
                )
                try:
                    payload = io.llm_client.complete_json(
                        prompt, "videoflow.script"
                    )
                    raw = payload.get("sections") if isinstance(payload, dict) else []
                    if isinstance(raw, list):
                        for item in raw:
                            if not isinstance(item, dict):
                                continue
                            sections.append(
                                {
                                    "id": len(sections) + 1,
                                    "title": str(item.get("title") or "Section"),
                                    "narration": str(item.get("narration") or ""),
                                    "visual": str(item.get("visual") or ""),
                                    "duration_sec": float(item.get("duration_sec") or 30),
                                }
                            )
                    if isinstance(payload, dict):
                        notes = str(payload.get("notes") or notes)
                    generated_by = "llm"
                except Exception as exc:  # noqa: BLE001 - keep the template
                    warnings.append(f"Script model fallback: {exc}")
                if len(sections) >= options.max_sections:
                    break
        if not sections:
            sections = _fallback_script(cases)[: options.max_sections]
        sections = sections[: options.max_sections]
        narration, edition = _render_script(sections)
        payload = {
            "topic": topic,
            "sections": sections,
            "notes": notes,
            "generated_by": generated_by,
            "warnings": warnings,
            "presenter": presenter[:2000],
        }
        _write_json(context.output / "script" / "script.json", payload)
        _write_text(context.output / "script" / "narration.txt", narration)
        _write_text(context.output / "script" / "edition.md", edition)
        context.metadata["script"] = payload
        context.artifacts["script_json"] = str(
            context.output / "script" / "script.json"
        )
        context.artifacts["script_narration"] = str(
            context.output / "script" / "narration.txt"
        )
        context.artifacts["script_edition"] = str(
            context.output / "script" / "edition.md"
        )
        context.hashes["script.dual_output"] = digest_payload(
            {"sections": len(sections), "generated_by": generated_by}
        )
        io.report(100, f"{len(sections)} script section(s) written")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("script_json", "script_narration", "script_edition")
            if context.artifacts.get(key)
        )

