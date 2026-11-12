from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.recipe import parse_recipe
from videoflow.engine.runner import RecipeRunner


def test_independent_research_steps_run_as_one_parallel_group(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out"
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "parallel_research",
            "name": "Parallel research",
            "steps": [
                {
                    "id": "research_a",
                    "type": "research.multi_agent",
                    "params": {"scopes": ["scope alpha"], "max_results": 1},
                },
                {
                    "id": "research_b",
                    "type": "research.multi_agent",
                    "params": {"scopes": ["scope beta"], "max_results": 1},
                },
            ],
        }
    )

    result = RecipeRunner(recipe).run(source, output, resume=False)

    aggregate = json.loads(
        (output / "research" / "agents.json").read_text(encoding="utf-8")
    )
    assert {item["agent_id"] for item in aggregate["agents"]} == {
        "scope-alpha",
        "scope-beta",
    }
    assert {run.id for run in result.step_runs} == {"research_a", "research_b"}
    assert (output / "research" / "agent_scope-alpha.json").is_file()
    assert (output / "research" / "agent_scope-beta.json").is_file()
    assert {item["agent_id"] for item in result.context.metadata["research_agents"]} == {
        "scope-alpha",
        "scope-beta",
    }


def test_parallel_research_reuses_source_stamp_and_intelligence(
    tmp_path: Path, monkeypatch
) -> None:
    import videoflow.application.intelligence as intelligence_module
    import videoflow.engine.runner as runner_module

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    output = tmp_path / "out"
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "parallel_research_reuse",
            "name": "Parallel research reuse",
            "steps": [
                {
                    "id": f"research_{name}",
                    "type": "research.multi_agent",
                    "params": {"scopes": [f"scope {name}"], "max_results": 1},
                }
                for name in ("a", "b", "c")
            ],
        }
    )
    calls = {"stamp": 0, "ai": 0}
    real_stamp = runner_module.source_fingerprint
    real_build = intelligence_module.build_intelligence

    def counting_stamp(path: Path) -> str:
        calls["stamp"] += 1
        return real_stamp(path)

    def counting_build(*args, **kwargs):
        calls["ai"] += 1
        return real_build(*args, **kwargs)

    monkeypatch.setattr(runner_module, "source_fingerprint", counting_stamp)
    monkeypatch.setattr(intelligence_module, "build_intelligence", counting_build)

    RecipeRunner(recipe).run(source, output, resume=False)

    assert calls == {"stamp": 1, "ai": 1}
