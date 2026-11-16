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


def test_channel_kit_mutates_recipe() -> None:
    from videoflow.application.channel_kit import apply_channel_kit
    from videoflow.core.recipe import parse_recipe
    from videoflow.domain.headless import ChannelKit, PresetHardConstraints, PresetRulebook

    recipe = parse_recipe(
        {
            "id": "kit",
            "name": "Kit",
            "steps": [
                {
                    "id": "select",
                    "type": "shorts.select",
                    "needs": [],
                    "params": {"aspect_ratio": "16:9"},
                },
                {
                    "id": "render",
                    "type": "shorts.render",
                    "needs": ["select"],
                    "params": {},
                },
                {
                    "id": "export",
                    "type": "export.video",
                    "needs": ["render"],
                    "params": {},
                },
                {
                    "id": "broll",
                    "type": "broll.plan",
                    "needs": ["select"],
                    "params": {},
                },
            ],
        }
    )
    book = PresetRulebook(
        channel_id="demo",
        hard_constraints=PresetHardConstraints(
            aspect_ratio="9:16", caption_preset="tiktok_bold", broll_style="emotional"
        ),
        channel_kit=ChannelKit(
            lut="/assets/look.cube",
            intro="/assets/intro.png",
            outro="/assets/outro.png",
            music=["/assets/music.mp3"],
            defaults={"shorts.select": {"target_duration_max_sec": 45}},
        ),
    )
    updated = apply_channel_kit(recipe, book)
    params = {step.id: step.params for step in updated.steps}
    assert params["select"]["aspect_ratio"] == "9:16"
    assert params["select"]["target_duration_max_sec"] == 45
    assert params["render"]["preset"] == "tiktok_bold"
    assert params["render"]["intro_path"] == "/assets/intro.png"
    assert params["render"]["music_path"] == "/assets/music.mp3"
    assert params["export"]["lut_path"] == "/assets/look.cube"
    assert params["broll"]["query"] == "emotional"


def test_channel_kit_ignores_unknown_step_metadata() -> None:
    from videoflow.application.channel_kit import apply_channel_kit
    from videoflow.core.recipe import parse_recipe
    from videoflow.domain.headless import ChannelKit, PresetRulebook

    recipe = parse_recipe(
        {
            "id": "unknown-kit",
            "name": "Unknown",
            "steps": [{"id": "x", "type": "custom.step", "needs": [], "params": {"a": 1}}],
        }
    )
    updated = apply_channel_kit(
        recipe,
        PresetRulebook(
            channel_id="demo",
            channel_kit=ChannelKit(defaults={"custom.step": {"b": 2}}),
        ),
    )
    assert updated.steps[0].params == {"a": 1}

    short = parse_recipe(
        {
            "id": "caption-kit",
            "name": "Caption",
            "steps": [
                {
                    "id": "render",
                    "type": "shorts.render",
                    "needs": [],
                    "params": {"caption_style": "bad"},
                }
            ],
        }
    )
    fixed = apply_channel_kit(short, PresetRulebook(channel_id="demo"))
    assert fixed.steps[0].params["caption_style"] == {}
