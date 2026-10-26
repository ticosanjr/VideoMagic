"""Recipe runner: LLM selection, through-order, plan, and checkpoints."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.core.context import PipelineContext
from videoflow.core.recipe import parse_recipe
from videoflow.domain.errors import RecipeError
from videoflow.engine import runner
from videoflow.engine.checkpoint import CHECKPOINT_VERSION, snapshot_context
from videoflow.engine.runner import RecipeRunner


def recipe(**llm: object) -> object:
    return parse_recipe(
        {
            "schema_version": 1,
            "id": "runner_test",
            "name": "Runner test",
            "llm": llm,
            "steps": [
                {"id": "ingest", "type": "ingest", "params": {}},
                {
                    "id": "vad",
                    "type": "audio.vad",
                    "needs": ["ingest"],
                    "params": {"engine": "ffmpeg"},
                },
            ],
        }
    )


def context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    work = output / "work"
    exports = output / "exports"
    for directory in (output, work, exports):
        directory.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    return PipelineContext(source=source, output=output, work=work, exports=exports)


def test_llm_none_returns_none() -> None:
    assert RecipeRunner(recipe())._build_llm(None) is None


def test_llm_opencode_builds_the_cli_adapter() -> None:
    runner_instance = RecipeRunner(recipe(provider="opencode", model="fast"))

    llm = runner_instance._build_llm(None)

    assert llm is not None
    assert llm.binary == "opencode"
    assert llm.model == "fast"


def test_llm_without_credentials_warns_and_returns_none(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOWFLOW_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_LLM_MODEL", raising=False)
    monkeypatch.setattr(
        "videoflow.application.providers.first_provider", lambda _capability: None
    )
    messages: list[tuple[str, str, str]] = []

    llm = RecipeRunner(recipe(provider="openai_compatible"))._build_llm(
        lambda module, level, message: messages.append((module, level, message))
    )

    assert llm is None
    assert any("continuing without it" in message for _, _, message in messages)


def test_llm_openai_compatible_uses_settings() -> None:
    llm = RecipeRunner(
        recipe(
            provider="openai_compatible",
            base_url="http://127.0.0.1:9/v1",
            model="test-model",
        )
    )._build_llm(None)

    assert llm is not None
    assert llm.base_url == "http://127.0.0.1:9/v1"
    assert llm.model == "test-model"


def test_through_keeps_dependencies_only() -> None:
    runner_instance = RecipeRunner(recipe())
    ordered = runner_instance.recipe.topological_order()

    assert [step.id for step in runner_instance._order_through(ordered, None)] == [
        "ingest",
        "vad",
    ]
    assert [step.id for step in runner_instance._order_through(ordered, "vad")] == [
        "ingest",
        "vad",
    ]


def test_through_rejects_unknown_or_disabled_steps() -> None:
    runner_instance = RecipeRunner(recipe())

    with pytest.raises(RecipeError, match="Unknown or disabled"):
        runner_instance._order_through(runner_instance.recipe.topological_order(), "nope")


def test_plan_reports_steps_and_variables() -> None:
    body = {
        "schema_version": 1,
        "id": "planned",
        "name": "Planned",
        "variables": {"speed": {"type": "string", "default": "fast"}},
        "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
    }
    runner_instance = RecipeRunner(parse_recipe(body))

    plan = runner_instance.plan(variables={"speed": "slow"})

    assert plan["ok"] is True
    assert plan["variables"] == {"speed": "slow"}
    assert plan["steps"][0]["id"] == "ingest"
    assert plan["steps"][0]["params"] == {}


def checkpoint_files(tmp_path: Path, context_value: PipelineContext) -> tuple[Path, Path]:
    directory = tmp_path / "step"
    directory.mkdir()
    manifest = directory / "manifest.json"
    snapshot = directory / "snapshot.json"
    return manifest, snapshot


def write_checkpoint(
    manifest: Path,
    snapshot: Path,
    context_value: PipelineContext,
    expected_fingerprint: str,
    **overrides: object,
) -> None:
    manifest_payload = {
        "v": CHECKPOINT_VERSION,
        "fingerprint": expected_fingerprint,
        "status": "succeeded",
    }
    snapshot_payload = {
        "v": CHECKPOINT_VERSION,
        "fingerprint": expected_fingerprint,
        "context": snapshot_context(context_value),
    }
    manifest_payload.update(overrides)
    manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
    snapshot.write_text(json.dumps(snapshot_payload), encoding="utf-8")


def fake_step(*outputs: Path) -> object:
    return SimpleNamespace(cache_outputs=lambda _context: tuple(outputs))


def test_checkpoint_requires_both_files(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    manifest, snapshot = checkpoint_files(tmp_path, ctx)

    assert (
        RecipeRunner(recipe())._load_checkpoint(
            ctx, fake_step(), manifest, snapshot, "fp"
        )
        is None
    )


@pytest.mark.parametrize("override", [{"v": 0}, {"fingerprint": "other"}, {"status": "failed"}])
def test_checkpoint_rejects_mismatched_manifests(tmp_path: Path, override: dict) -> None:
    ctx = context(tmp_path)
    manifest, snapshot = checkpoint_files(tmp_path, ctx)
    write_checkpoint(manifest, snapshot, ctx, "fp", **override)

    assert (
        RecipeRunner(recipe())._load_checkpoint(
            ctx, fake_step(), manifest, snapshot, "fp"
        )
        is None
    )


def test_checkpoint_rejects_mismatched_snapshot(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    manifest, snapshot = checkpoint_files(tmp_path, ctx)
    write_checkpoint(manifest, snapshot, ctx, "fp")
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    payload["fingerprint"] = "other"
    snapshot.write_text(json.dumps(payload), encoding="utf-8")

    assert (
        RecipeRunner(recipe())._load_checkpoint(
            ctx, fake_step(), manifest, snapshot, "fp"
        )
        is None
    )


def test_checkpoint_rejects_unreadable_snapshots(tmp_path: Path, monkeypatch) -> None:
    ctx = context(tmp_path)
    manifest, snapshot = checkpoint_files(tmp_path, ctx)
    write_checkpoint(manifest, snapshot, ctx, "fp")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise ValueError("corrupt")

    monkeypatch.setattr(runner, "restore_context", fail)

    assert (
        RecipeRunner(recipe())._load_checkpoint(
            ctx, fake_step(), manifest, snapshot, "fp"
        )
        is None
    )


def test_checkpoint_requires_outputs_to_exist(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    manifest, snapshot = checkpoint_files(tmp_path, ctx)
    write_checkpoint(manifest, snapshot, ctx, "fp")
    missing = tmp_path / "missing.mp4"

    assert (
        RecipeRunner(recipe())._load_checkpoint(
            ctx, fake_step(missing), manifest, snapshot, "fp"
        )
        is None
    )


def test_checkpoint_restores_and_returns_existing_outputs(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    manifest, snapshot = checkpoint_files(tmp_path, ctx)
    write_checkpoint(manifest, snapshot, ctx, "fp")
    output = tmp_path / "artifact.mp4"
    output.write_bytes(b"x")

    restored = RecipeRunner(recipe())._load_checkpoint(
        ctx, fake_step(output), manifest, snapshot, "fp"
    )

    assert restored == (str(output),)
    assert ctx.source == tmp_path / "source.mp4"
