"""Preset schema v2 hard/learned separation and channel kit."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.preset_rules import load_rulebook, save_rulebook
from videoflow.core.context import PipelineContext
from videoflow.domain.headless import PresetRule, PresetRulebook
from videoflow.steps.base import StepIO
from videoflow.steps.preset_compile import CompileRuleParams, CompileRuleStep


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir()
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_hard_constraints_survive_replace_and_rules_cap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    book = PresetRulebook(
        channel_id="demo",
        hard_constraints={"palette": "light", "cut_rhythm_sec": 4.0},
        learned_rules=[
            PresetRule(id=f"r{i}", text=f"Rule number {i}", scope="learned") for i in range(15)
        ],
    )
    save_rulebook(book)
    context = _context(tmp_path)
    CompileRuleStep().run(
        context,
        CompileRuleParams(channel_id="demo", review_notes=["Brand new rule"]),
        StepIO(),
    )
    updated = load_rulebook("demo")
    assert len(updated.learned_rules) == 15
    assert updated.hard_constraints.palette == "light"

    CompileRuleStep().run(
        context,
        CompileRuleParams(channel_id="demo", mode="replace", review_notes=["Only rule"]),
        StepIO(),
    )
    replaced = load_rulebook("demo")
    assert [rule.text for rule in replaced.learned_rules] == ["Only rule"]
    assert replaced.hard_constraints.cut_rhythm_sec == 4.0


def test_legacy_rulebook_migrates_and_similar_rules_merge(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    channel = tmp_path / "home" / "channels"
    channel.mkdir(parents=True)
    (channel / "legacy.json").write_text(
        json.dumps({"channel_id": "legacy", "rules": [{"id": "r1", "text": "keep"}]}),
        encoding="utf-8",
    )
    migrated = load_rulebook("legacy")
    assert migrated.schema_version == 2
    assert migrated.learned_rules[0].text == "keep"

    context = _context(tmp_path)
    CompileRuleStep().run(
        context,
        CompileRuleParams(
            channel_id="legacy",
            review_notes=["use open loops often", "use open loops often please"],
        ),
        StepIO(),
    )
    book = load_rulebook("legacy")
    assert len(book.learned_rules) == 2
    assert any("please" in rule.text for rule in book.learned_rules)
    assert book.channel_kit.fonts == []
