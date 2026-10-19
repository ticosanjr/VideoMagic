import json
from pathlib import Path

from videoflow.domain.state import ApiError, JobRecord, LlmRetakeResponse, Preset, ProjectState

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

MODELS = {
    "project-state": ProjectState,
    "preset": Preset,
    "llm-retake-response": LlmRetakeResponse,
    "api-error": ApiError,
    "job-record": JobRecord,
}


def test_committed_schemas_match_the_models() -> None:
    for name, model in MODELS.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        committed = json.loads(path.read_text(encoding="utf-8"))
        assert committed == model.model_json_schema(), f"{name} is out of date"


def test_no_public_schema_exposes_an_api_key() -> None:
    for model in MODELS.values():
        assert "api_key" not in json.dumps(model.model_json_schema())
