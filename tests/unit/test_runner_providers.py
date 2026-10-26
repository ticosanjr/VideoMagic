"""Runner provider resolution for ASR and TTS nodes."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.test_recipe import FakeAdapter
from videoflow.application.providers import ProviderConfig, upsert_provider
from videoflow.core.recipe import parse_recipe
from videoflow.domain.errors import RecipeError
from videoflow.engine.runner import RecipeRunner


def recipe(provider_id: str, step_type: str = "transcribe") -> object:
    stage = {"id": "stage", "type": step_type, "needs": ["ingest"], "params": {}}
    if step_type == "transcribe":
        stage["params"] = {"provider_id": provider_id, "mode": "none"}
    else:
        stage["params"] = {"provider_id": provider_id}
        stage["needs"] = ["ingest"]
    return parse_recipe(
        {
            "schema_version": 1,
            "id": "providers",
            "name": "Providers",
            "steps": [{"id": "ingest", "type": "ingest", "params": {}}, stage],
        }
    )


def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.mp4"
    path.write_bytes(b"x")
    return path


def test_runner_accepts_a_matching_provider(tmp_path: Path) -> None:
    upsert_provider(
        ProviderConfig(
            id="asr-demo",
            name="ASR demo",
            capability="asr",
            base_url="http://127.0.0.1:9/v1",
            model="whisper-1",
            api_key_env="VIDEOFLOW_ASR_KEY",
        )
    )

    result = RecipeRunner(recipe("asr-demo"), adapter=FakeAdapter()).run(
        source(tmp_path), tmp_path / "out", resume=False
    )

    assert result.recipe_id == "providers"
    assert result.context.transcript_source == "none"


def test_runner_rejects_unknown_providers(tmp_path: Path) -> None:
    with pytest.raises(RecipeError, match="unknown provider"):
        RecipeRunner(recipe("missing"), adapter=FakeAdapter()).run(
            source(tmp_path), tmp_path / "out", resume=False
        )


def test_runner_rejects_a_provider_from_another_capability(tmp_path: Path) -> None:
    upsert_provider(
        ProviderConfig(
            id="tts-demo",
            name="TTS demo",
            capability="tts",
            base_url="http://127.0.0.1:9/v1",
            model="tts-1",
        )
    )

    with pytest.raises(RecipeError, match="not a asr provider"):
        RecipeRunner(recipe("tts-demo"), adapter=FakeAdapter()).run(
            source(tmp_path), tmp_path / "out", resume=False
        )
