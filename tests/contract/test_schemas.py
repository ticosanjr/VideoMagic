import json
from pathlib import Path

from videoflow.core.recipe import Recipe
from videoflow.domain.state import ApiError, JobRecord, LlmRetakeResponse, Preset, ProjectState

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

MODELS = {
    "project-state": ProjectState,
    "preset": Preset,
    "llm-retake-response": LlmRetakeResponse,
    "api-error": ApiError,
    "job-record": JobRecord,
    "recipe": Recipe,
}


def test_committed_schemas_match_the_models() -> None:
    for name, model in MODELS.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        committed = json.loads(path.read_text(encoding="utf-8"))
        assert committed == model.model_json_schema(), f"{name} is out of date"


def _property_names(schema: object) -> set[str]:
    names: set[str] = set()
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            names.update(str(name) for name in properties)
        for value in schema.values():
            names.update(_property_names(value))
    elif isinstance(schema, list):
        for value in schema:
            names.update(_property_names(value))
    return names


def test_no_public_schema_exposes_an_api_key() -> None:
    for model in MODELS.values():
        assert "api_key" not in _property_names(model.model_json_schema())
