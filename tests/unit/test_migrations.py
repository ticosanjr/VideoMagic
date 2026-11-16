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
    assert payload["schema_version"] == 2


def test_project_state_v1_is_migrated_to_multi_source() -> None:
    payload = migrate_project_state(
        {
            "schema_version": 1,
            "media_info": {
                "source_path": "/tmp/a.mp4",
                "duration_frames": 30,
                "fps_num": 30,
                "fps_den": 1,
                "width": 320,
                "height": 240,
                "audio_sample_rate": 48000,
            },
            "video_segments": [
                {
                    "clip_id": "v1",
                    "source_in_frame": 0,
                    "source_out_frame": 30,
                    "timeline_in_frame": 0,
                    "timeline_out_frame": 30,
                }
            ],
        }
    )
    assert payload["schema_version"] == 2
    assert payload["primary_source_id"] == "primary"
    assert payload["video_segments"][0]["source_id"] == "primary"


def test_future_project_state_version_is_rejected() -> None:
    with pytest.raises(ProjectStateError):
        migrate_project_state({"schema_version": 9})
