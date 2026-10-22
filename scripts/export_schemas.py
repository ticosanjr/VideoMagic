"""Write the committed JSON Schemas from the Pydantic models.

Run after changing a domain model:

    uv run python scripts/export_schemas.py
"""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.recipe import Recipe
from videoflow.domain.state import ApiError, JobRecord, LlmRetakeResponse, Preset, ProjectState

MODELS = {
    "project-state": ProjectState,
    "preset": Preset,
    "llm-retake-response": LlmRetakeResponse,
    "api-error": ApiError,
    "job-record": JobRecord,
    "recipe": Recipe,
}


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "schemas"
    target.mkdir(exist_ok=True)
    for name, model in MODELS.items():
        payload = json.dumps(model.model_json_schema(), indent=2, sort_keys=True)
        (target / f"{name}.schema.json").write_text(payload + "\n", encoding="utf-8")
        print(f"wrote {name}.schema.json")


if __name__ == "__main__":
    main()
