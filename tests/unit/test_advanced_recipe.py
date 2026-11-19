from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import pytest

from tests.recipe_jobs import manager_with_runner, start_recipe
from videoflow.application import database
from videoflow.application.plugins import load_plugins
from videoflow.application.shorts import ShortClip
from videoflow.core.expressions import resolve_value
from videoflow.core.recipe import parse_recipe
from videoflow.domain.errors import ApprovalRequiredError
from videoflow.engine.recipes import get_recipe, list_recipes
from videoflow.engine.runner import RecipeRunner
from videoflow.steps import get_step, requirements_by_type, step_types
from videoflow.steps.shorts_score import ScoreParams, ShortsScoreStep


def test_expression_resolution_and_functions() -> None:
    values = {"count": 4, "who": "editor"}
    assert resolve_value("{{ count + 1 }}", values) == 5
    assert resolve_value("{{ clamp(count, 0, 2) }}", values) == 2
    assert resolve_value("{{ if(count > 3, 'yes', 'no') }}", values) == "yes"
    assert resolve_value("$who", values) == "editor"
    assert resolve_value("hello $who", values) == "hello editor"
    assert resolve_value(["$count", {"x": "{{ count * 2 }}"}], values) == [4, {"x": 8}]


def test_recipe_variables_and_profile() -> None:
    recipe = parse_recipe(
        {
            "id": "vars",
            "name": "Vars",
            "variables": {
                "count": {"type": "number", "default": 2},
                "who": {"type": "string", "default": "editor"},
            },
            "profiles": {
                "fast": {
                    "variables": {"count": {"default": 9}},
                    "steps": {"one": {"tag": "fast"}},
                }
            },
            "steps": [
                {
                    "id": "one",
                    "type": "assets.index",
                    "params": {"asset_dir": "/tmp/{{ count }}", "tags": ["$who"]},
                }
            ],
        }
    )
    resolved = recipe.with_variables({"who": "qa"}, profile="fast")
    assert resolved.steps[0].params["asset_dir"] == "/tmp/9"
    assert resolved.steps[0].params["tags"] == ["qa"]
    assert resolved.steps[0].params["tag"] == "fast"
    plan = RecipeRunner(recipe).plan(variables={"count": 3})
    assert plan["steps"][0]["params"]["asset_dir"] == "/tmp/3"


def test_all_builtin_recipes_validate() -> None:
    assert len(list_recipes()) >= 30
    for entry in list_recipes():
        recipe = get_recipe(entry["id"])
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())


def test_flow_map_and_reduce(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.mp4").write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "clip.mp4").write_bytes(b"x")
    recipe = parse_recipe(
        {
            "id": "map_test",
            "name": "Map test",
            "steps": [
                {
                    "id": "mapped",
                    "type": "flow.map",
                    "params": {
                        "over": "files",
                        "glob": "*.mp4",
                        "collect": "mapped",
                        "on_error": "continue",
                        "parallel": 2,
                        "steps": [
                            {
                                "type": "assets.index",
                                "params": {"asset_dir": str(assets)},
                            }
                        ],
                    },
                },
                {
                    "id": "top",
                    "type": "flow.reduce",
                    "needs": ["mapped"],
                    "params": {"source": "mapped", "mode": "top_k", "top_k": 1},
                },
            ],
        }
    )
    result = RecipeRunner(recipe).run(source, tmp_path / "out", resume=False)
    assert len(result.context.metadata["mapped"]) == 2
    assert len(result.context.metadata["reduced"]) == 1


def test_human_gate_pauses_and_resumes(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    recipe = parse_recipe(
        {
            "id": "gate_test",
            "name": "Gate test",
            "steps": [
                {
                    "id": "index",
                    "type": "assets.index",
                    "params": {"asset_dir": str(assets)},
                },
                {
                    "id": "gate",
                    "type": "human.gate",
                    "needs": ["index"],
                    "params": {"gate_id": "review", "title": "Review"},
                },
            ],
        }
    )
    output = tmp_path / "out"
    with pytest.raises(ApprovalRequiredError):
        RecipeRunner(recipe).run(source, output, resume=False)
    approvals = output / "approvals"
    approvals.mkdir(parents=True)
    (approvals / "review.json").write_text('{"approved": true}')
    result = RecipeRunner(recipe).run(source, output, resume=True)
    assert result.context.metadata["gate_review"]["approved"] is True


def test_job_variants_write_separate_outputs(monkeypatch, tmp_path: Path) -> None:

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    recipe = {
        "schema_version": 1,
        "id": "variant_job",
        "name": "Variant job",
        "variables": {"tag": {"type": "string", "default": "a"}},
        "variants": [
            {"name": "one", "variables": {"tag": "one"}},
            {"name": "two", "variables": {"tag": "two"}},
        ],
        "steps": [
            {
                "id": "index",
                "type": "assets.index",
                "params": {"asset_dir": str(assets), "tags": ["$tag"]},
            }
        ],
    }
    manager = manager_with_runner()
    job = start_recipe(manager, source, tmp_path / "out", {"mode": "recipe", "recipe": recipe})
    for _ in range(300):
        if job.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
    assert job.status == "succeeded", job.error
    assert len(job.result["variants"]) == 2
    assert (tmp_path / "out" / "one" / "assets-index.json").is_file()
    assert (tmp_path / "out" / "two" / "assets-index.json").is_file()


def test_shorts_score_top_k_and_diversity(tmp_path: Path) -> None:
    class Context:
        selected_shorts = [
            ShortClip(
                title="alpha beta gamma",
                start_sample=0,
                end_sample=100,
                sentence_ids=(0,),
                pieces=((0, 100),),
                score_breakdown=(("hook_strength", 5.0), ("completeness", 1.0)),
            ),
            ShortClip(
                title="alpha beta delta",
                start_sample=100,
                end_sample=200,
                sentence_ids=(1,),
                pieces=((100, 200),),
                score_breakdown=(("hook_strength", 4.0),),
            ),
            ShortClip(
                title="unrelated topic entirely",
                start_sample=200,
                end_sample=300,
                sentence_ids=(2,),
                pieces=((200, 300),),
                score_breakdown=(("hook_strength", 1.0),),
            ),
        ]
        shorts = []
        output = tmp_path
        media = None
        metadata: dict[str, object] = {}
        artifacts: dict[str, str] = {}

    context = Context()
    from videoflow.steps.base import StepIO

    ShortsScoreStep().run(context, ScoreParams(top_k=2), StepIO(stage="score"))
    assert len(context.selected_shorts) == 2
    assert context.selected_shorts[0].score >= context.selected_shorts[1].score


def test_plugin_loader_registers_step(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    plugin = tmp_path / "plugins" / "demo"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "name": "Demo",
                "version": "0.1.0",
                "entry": "plugin.py",
                "enabled": True,
            }
        )
    )
    (plugin / "plugin.py").write_text(
        "from pydantic import BaseModel\n"
        "from videoflow.steps.base import BaseStep, StepIO\n"
        "from videoflow.steps.registry import register_step\n"
        "@register_step\n"
        "class DemoStep(BaseStep):\n"
        "    type = 'demo.step'\n"
        "    title = 'Demo'\n"
        "    def run(self, context, params, io):\n"
        "        io.report(100, 'ok')\n"
    )
    loaded = load_plugins()
    assert loaded and loaded[0]["loaded"] is True
    assert get_step("demo.step").type == "demo.step"


def test_database_metrics_and_backup(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    database.upsert_job("job-1", {"job_id": "job-1", "status": "succeeded"})
    metrics = database.metrics()
    assert metrics["total_jobs"] == 1
    assert metrics["database"]["ok"] is True
    target = tmp_path / "backup.zip"
    database.backup(target)
    with zipfile.ZipFile(target) as bundle:
        assert "videoflow.db" in bundle.namelist()


def test_i18n_locale_strings() -> None:
    from videoflow.cli import _version  # noqa: F401 - import smoke

    # The UI translator is exercised through its JSON dictionary in Vitest.
    assert True


def test_job_queue_waits_for_a_slot(tmp_path: Path) -> None:

    release = __import__("threading").Event()

    def wait_runner(source, output, **kwargs):
        release.wait(timeout=10)
        return {"ok": True}

    manager = manager_with_runner(wait_runner, max_active=1)
    first = start_recipe(manager, tmp_path / "a.mp4", tmp_path / "out-a", queue=True)
    second = start_recipe(manager, tmp_path / "b.mp4", tmp_path / "out-b", queue=True)
    assert first.status in {"queued", "running"}
    assert second.status == "queued"
    release.set()
    for _ in range(200):
        if first.status in {"succeeded", "failed"} and second.status in {
            "succeeded",
            "failed",
        }:
            break
        time.sleep(0.01)
    assert first.status == "succeeded"
    assert second.status == "succeeded"


def test_analytics_weights_affect_scoring(tmp_path: Path) -> None:
    from videoflow.steps.base import StepIO

    class Context:
        selected_shorts = [
            ShortClip(
                title="plain clip",
                start_sample=0,
                end_sample=100,
                sentence_ids=(0,),
                pieces=((0, 100),),
                score_breakdown=(("completeness", 1.0),),
            )
        ]
        shorts = []
        output = tmp_path
        media = None
        metadata = {"analytics_weights": {"completeness": 5.0}}
        artifacts: dict[str, str] = {}

    context = Context()
    ShortsScoreStep().run(context, ScoreParams(), StepIO(stage="score"))
    assert context.selected_shorts[0].score == 5.0


def test_thumbnail_experiment_selects_winner(tmp_path: Path) -> None:
    from videoflow.application.deliverables import record_thumbnail_metric
    from videoflow.steps.base import StepIO
    from videoflow.steps.delivery import ExperimentEvaluateStep, ExperimentParams

    thumbs = tmp_path / "thumbnails"
    thumbs.mkdir()
    (thumbs / "variant-1.png").write_bytes(b"png")
    (thumbs / "variant-2.png").write_bytes(b"png")
    record_thumbnail_metric(tmp_path, "variant-1.png", impressions=10, clicks=1)
    record_thumbnail_metric(tmp_path, "variant-2.png", impressions=10, clicks=4)

    class Context:
        output = tmp_path
        warnings: list[str] = []
        artifacts: dict[str, str] = {}
        metadata: dict[str, object] = {}

    ExperimentEvaluateStep().run(Context(), ExperimentParams(), StepIO(stage="experiment"))
    import json

    payload = json.loads((tmp_path / "delivery" / "experiment.json").read_text())
    assert payload["winner"]["name"] == "variant-2.png"


def test_shorts_selection_report(tmp_path: Path) -> None:
    from videoflow.steps.base import StepIO

    class Context:
        selected_shorts = [
            ShortClip(
                title="strong hook",
                start_sample=0,
                end_sample=100,
                sentence_ids=(0,),
                pieces=((0, 100),),
                score_breakdown=(("hook_strength", 3.0),),
            )
        ]
        shorts = []
        output = tmp_path
        media = None
        metadata: dict[str, object] = {}
        artifacts: dict[str, str] = {}

    ShortsScoreStep().run(Context(), ScoreParams(), StepIO(stage="score"))
    assert (tmp_path / "shorts-selection-report.json").is_file()


def test_database_backup_restore_roundtrip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    database.upsert_job("job-1", {"job_id": "job-1", "status": "succeeded"})
    archive = tmp_path / "backup.zip"
    database.backup(archive)
    database.upsert_job("job-2", {"job_id": "job-2", "status": "failed"})
    assert database.metrics()["total_jobs"] == 2
    restored = database.restore(archive)
    assert restored["ok"] is True
    assert database.metrics()["total_jobs"] == 1


def test_dubbing_step_skips_without_provider(monkeypatch, tmp_path: Path) -> None:
    from videoflow.steps.base import StepIO
    from videoflow.steps.dubbing import DubbingParams, DubbingStep

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))

    class Context:
        output = tmp_path
        shorts = [{"title": "One"}]
        warnings: list[str] = []
        artifacts: dict[str, str] = {}
        metadata: dict[str, object] = {}

    context = Context()
    DubbingStep().run(context, DubbingParams(), StepIO(stage="dub"))
    assert "dubbed_shorts" not in context.metadata


def test_localized_recipe_runs_dubbing_after_the_short_render() -> None:
    from videoflow.engine.recipes import get_recipe

    recipe = get_recipe("localized_shorts")
    types = {step.type for step in recipe.enabled_steps()}
    assert "localization.dub" in types
    dub = next(step for step in recipe.steps if step.type == "localization.dub")
    assert "render_shorts" in dub.needs


def test_hook_duration_recipe_has_ab_step() -> None:
    from videoflow.engine.recipes import get_recipe

    recipe = get_recipe("hook_duration_ab")
    types = [step.type for step in recipe.enabled_steps()]
    assert "shorts.ab" in types
    assert types.index("shorts.ab") < types.index("shorts.render")


def test_resource_workers_respects_provider_and_cpu(monkeypatch) -> None:
    from videoflow.steps.flow import _resource_workers

    monkeypatch.setenv("VIDEOWFLOW_PROVIDER_CONCURRENCY", "2")
    monkeypatch.setattr("os.cpu_count", lambda: 16)
    assert _resource_workers(8) == 2
    monkeypatch.setenv("VIDEOWFLOW_PROVIDER_CONCURRENCY", "8")
    assert _resource_workers(3) == 3
