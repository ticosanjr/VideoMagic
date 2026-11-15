"""Compile human review notes into durable channel rules."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from videoflow.application.preset_rules import (
    load_rulebook,
    normal,
    rule_id,
    save_rulebook,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.headless import PresetRule, PresetRulebook
from videoflow.steps.base import BaseStep, StepIO
from videoflow.steps.registry import register_step


class CompileRuleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_id: str = Field(default="default", min_length=1, max_length=120)
    review_notes: list[str] = Field(default_factory=list)
    mode: str = Field(default="merge", pattern="^(merge|replace)$")
    max_rules: int = Field(default=200, ge=1, le=2000)


@register_step
class CompileRuleStep(BaseStep):
    type = "preset.compile_rule"
    status = "available"
    icon = "⚙"
    color = "#a855f7"
    title = "Compile preset rules"
    description = "Merge review notes into a channel rulebook, deduplicating conflicts."
    requires = ()
    produces = ("preset_rulebook",)
    params_model = CompileRuleParams

    def run(self, context: PipelineContext, params: BaseModel, io: StepIO) -> None:
        options = CompileRuleParams.model_validate(params)
        book = (
            PresetRulebook(channel_id=options.channel_id)
            if options.mode == "replace"
            else load_rulebook(options.channel_id)
        )
        existing = {normal(rule.text): rule for rule in book.rules}
        now = datetime.now(UTC).isoformat(timespec="seconds")
        added = 0
        for note in options.review_notes:
            text = str(note).strip()
            if not text:
                continue
            key = normal(text)
            if key in existing:
                existing[key].weight = min(5.0, existing[key].weight + 0.25)
                continue
            rule = PresetRule(
                id=rule_id(text),
                text=text,
                source="review_notes",
                created_at=now,
            )
            book.rules.append(rule)
            existing[key] = rule
            added += 1
        book.rules.sort(key=lambda rule: (-rule.weight, rule.created_at, rule.id))
        book.rules = book.rules[: options.max_rules]
        path = save_rulebook(book)
        context.metadata["preset_rulebook"] = book.model_dump(mode="json")
        context.artifacts["preset_rulebook"] = str(path)
        context.hashes["preset_rules"] = str(book.version)
        io.report(100, f"{added} rule(s) added, {len(book.rules)} active")
