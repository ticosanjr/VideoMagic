"""Persistent project rulebooks for autonomous runs."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videoflow.core.context import PipelineContext
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.common import digest_payload
from videoflow.steps.registry import register_step

_DUCK = re.compile(r"music_ducking_level\s*=\s*([-\d.]+)\s*dB", re.IGNORECASE)


class RulesMemoryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(default_factory=lambda: ["agents.md", "claude.md"])
    rules: list[str] = Field(default_factory=list)
    dedupe: bool = True
    base_dir: str = ""


def _consolidate(text: str, dedupe: bool) -> str:
    matches = _DUCK.findall(text)
    if matches:
        latest = matches[-1]
        text = _DUCK.sub(f"music_ducking_level = {latest}dB", text)
    if not dedupe:
        return text
    lines = text.splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            output.append(line)
            continue
        if stripped in seen:
            continue
        seen.add(stripped)
        output.append(line)
    return "\n".join(output).rstrip() + "\n"


@register_step
class RulesMemoryStep(BaseStep):
    type = "rules.memory"
    title = "Rules memory"
    description = (
        "Append learned directives to agents.md/claude.md and consolidate "
        "duplicate rules to keep the context small."
    )
    status = "available"
    icon = "▤"
    color = "#22c55e"
    produces = ("rules_memory",)
    params_model = RulesMemoryParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = RulesMemoryParams.model_validate(params)
        base = (
            Path(options.base_dir).expanduser()
            if options.base_dir
            else context.output
        )
        base.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for raw in options.paths:
            path = Path(raw).expanduser()
            target = path if path.is_absolute() else base / path
            target.parent.mkdir(parents=True, exist_ok=True)
            text = (
                target.read_text(encoding="utf-8")
                if target.is_file()
                else "# Project rules\n"
            )
            if options.rules:
                if "## Learned rules" not in text:
                    text = text.rstrip() + "\n\n## Learned rules\n"
                text = text.rstrip() + "\n" + "\n".join(
                    f"- {rule.strip()}" for rule in options.rules if rule.strip()
                )
                text += "\n"
            target.write_text(_consolidate(text, options.dedupe), encoding="utf-8")
            written.append(str(target))
        report = {"files": written, "rules": len(options.rules)}
        context.metadata["rules_memory"] = report
        target = context.output / "rules-memory.json"
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        context.artifacts["rules_memory"] = str(target)
        context.hashes["rules.memory"] = digest_payload(report)
        io.report(100, f"Rulebook updated ({len(written)} file(s))")

    def cache_outputs(self, context: PipelineContext) -> tuple[Path, ...]:
        path = context.artifacts.get("rules_memory")
        return (Path(path),) if path else ()
