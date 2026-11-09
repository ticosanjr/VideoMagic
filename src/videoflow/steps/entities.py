"""Apply human entity corrections to the narrative manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step

_MAPPING = re.compile(r"\s*(?:->|=>|\|)\s*")


class EntityApplyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corrections_path: str = Field(default="entities/corrections.json", max_length=2000)
    narrative_path: str = Field(default="narrative/entities.json", max_length=2000)
    output_stem: str = Field(default="entities-corrected", max_length=120)


def _mappings(answers: dict[str, Any]) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for key in ("people_corrections", "visual_corrections", "metric_corrections"):
        text = str(answers.get(key) or "")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = _MAPPING.split(line, maxsplit=1)
            if len(parts) != 2:
                continue
            source, target = parts[0].strip(), parts[1].strip()
            if source and target:
                mappings[source] = target
    return mappings


def _replace(value: Any, mappings: dict[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for source, target in sorted(mappings.items(), key=lambda item: -len(item[0])):
            result = result.replace(source, target)
        return result
    if isinstance(value, list):
        return [_replace(item, mappings) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, mappings) for key, item in value.items()}
    return value


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


@register_step
class EntityApplyStep(BaseStep):
    type = "entities.apply"
    title = "Apply entity corrections"
    description = (
        "Apply human phonetic, name, object, and metric corrections to the "
        "narrative entity manifest and write a reviewable before/after report."
    )
    status = "available"
    icon = "✎"
    color = "#a78bfa"
    params_model = EntityApplyParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = EntityApplyParams.model_validate(params)
        corrections = _read_json(context.output / options.corrections_path, {})
        answers = corrections.get("answers", {}) if isinstance(corrections, dict) else {}
        mappings = _mappings(answers if isinstance(answers, dict) else {})
        manifest = _read_json(context.output / options.narrative_path, {})
        if not manifest:
            manifest = context.metadata.get("narrative_entities", {})
        corrected = _replace(manifest, mappings)
        payload = {
            "corrections": mappings,
            "corrected_count": len(mappings),
            "manifest": corrected,
        }
        json_path = context.output / "narrative" / f"{options.output_stem}.json"
        markdown_path = context.output / "narrative" / f"{options.output_stem}.md"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(corrected, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        lines = ["# Entity corrections", ""]
        if mappings:
            for source, target in sorted(mappings.items()):
                lines.append(f"- `{source}` → `{target}`")
        else:
            lines.append("No corrections were supplied.")
        markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        context.metadata["entity_corrections"] = payload
        context.metadata["narrative_entities_corrected"] = corrected
        context.artifacts["entities_corrected"] = str(json_path)
        context.artifacts["entities_corrected_md"] = str(markdown_path)
        context.hashes["entities.apply"] = digest_payload(payload)
        io.report(100, f"{len(mappings)} entity correction(s) applied")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        return tuple(
            Path(context.artifacts[key])
            for key in ("entities_corrected", "entities_corrected_md")
            if context.artifacts.get(key)
        )
