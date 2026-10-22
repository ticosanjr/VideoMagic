import pytest

from videoflow.core.recipe import parse_recipe
from videoflow.domain.errors import ProjectStateError, RecipeError
from videoflow.domain.migrations import migrate_project_state, migrate_recipe


def test_old_recipe_without_version_or_optional_fields_is_migrated() -> None:
    recipe = parse_recipe(
        {
            "id": "old",
            "name": "Old",
            "steps": [{"id": "ingest", "type": "ingest"}],
        }
    )
    assert recipe.schema_version == 1
    assert recipe.steps[0].enabled is True
    assert recipe.steps[0].needs == []
    assert recipe.steps[0].params == {}


def test_future_recipe_version_is_rejected() -> None:
    with pytest.raises(RecipeError):
        migrate_recipe({"schema_version": 2, "steps": []})


def test_project_state_without_version_is_migrated() -> None:
    payload = migrate_project_state({"project_id": "00000000-0000-0000-0000-000000000000"})
    assert payload["schema_version"] == 1


def test_future_project_state_version_is_rejected() -> None:
    with pytest.raises(ProjectStateError):
        migrate_project_state({"schema_version": 9})
