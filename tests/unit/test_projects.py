import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from videoflow.application.presets import (
    get_preset,
    load_presets,
    save_preset,
    validate_preset_name,
)
from videoflow.application.projects import (
    ProjectStore,
    apply_media,
    apply_module_config,
    apply_module_enabled,
    apply_overrides,
    apply_preset,
)
from videoflow.application.storage import atomic_write_text
from videoflow.domain.errors import (
    InvalidOverrideError,
    InvalidPresetNameError,
    PathJailError,
    PresetError,
    PresetNotFoundError,
    ProjectNotFoundError,
    ProjectStateError,
    UnknownModuleError,
    WordOverridesNotSupportedError,
)
from videoflow.domain.presets import load_shipped_presets
from videoflow.domain.state import (
    ManualOverride,
    MediaInfo,
    Sentence,
    WordTiming,
)


@pytest.fixture
def store(monkeypatch, tmp_path: Path) -> ProjectStore:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    return ProjectStore(home=tmp_path / "home")


def media(tmp_path: Path) -> MediaInfo:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    return MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )


def test_store_revisions_survive_a_new_instance(store: ProjectStore, tmp_path: Path) -> None:
    record, state = store.create(tmp_path / "project")
    assert state.revision == 1
    assert (record.videoflow_dir / "revisions" / "000001.json").is_file()

    state = state.model_copy(update={"cache_hashes": {"ingest": "abc"}})
    saved, updated = store.save_state(record.project_id, state)
    assert saved.revision == 2
    assert updated.revision == 2
    assert (record.videoflow_dir / "revisions" / "000002.json").is_file()

    reopened = ProjectStore(home=tmp_path / "home")
    assert reopened.get(record.project_id).revision == 2
    assert reopened.read_state(record.project_id).cache_hashes == {"ingest": "abc"}
    assert reopened.list()[0].project_id == record.project_id


def test_store_records_job_state_without_incrementing(store: ProjectStore, tmp_path: Path) -> None:
    record, state = store.create(tmp_path / "project")
    state = state.model_copy(update={"revision": 7})
    atomic_write_text(record.state_path, state.model_dump_json(indent=2) + "\n")
    revived = store.record_job_state(record.project_id)
    assert revived.revision == 7
    assert store.get(record.project_id).revision == 7
    assert (record.videoflow_dir / "revisions" / "000007.json").is_file()
    store.record_job_state(record.project_id)
    assert len(list((record.videoflow_dir / "revisions").glob("*.json"))) == 2


def test_store_rejects_deleted_or_outside_projects(store: ProjectStore, tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        store.get(uuid4())
    with pytest.raises(ProjectNotFoundError):
        store.get("not-a-uuid")
    with pytest.raises(PathJailError):
        store.create(tmp_path.parent / "outside")


def test_store_reports_corrupt_registry_and_state(store: ProjectStore, tmp_path: Path) -> None:
    record, _state = store.create(tmp_path / "project")
    (tmp_path / "home" / "projects.json").write_text("{", encoding="utf-8")
    with pytest.raises(ProjectStateError):
        store.list()

    (tmp_path / "home" / "projects.json").write_text(
        json.dumps({"projects": [{"project_id": "bad"}]}), encoding="utf-8"
    )
    with pytest.raises(ProjectStateError):
        store.list()

    (tmp_path / "home" / "projects.json").write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "project_id": str(record.project_id),
                        "root": str(record.root),
                        "revision": 1,
                        "created_at": "now",
                        "updated_at": "now",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    record.state_path.write_text("{", encoding="utf-8")
    with pytest.raises(ProjectStateError):
        store.read_state(record.project_id)


def test_state_helpers_invalidate_and_validate(store: ProjectStore, tmp_path: Path) -> None:
    _record, state = store.create(tmp_path / "project")
    source = media(tmp_path)
    state = apply_media(state, source)
    assert state.media_info == source

    word = WordTiming(word="x", start_sample=0, end_sample=10, probability=0.9)
    state = state.model_copy(
        update={
            "transcript": [
                Sentence(
                    id=0,
                    start_sample=0,
                    end_sample=10,
                    text="x",
                    words=[word],
                )
            ]
        }
    )
    overridden = apply_overrides(
        state, [ManualOverride(sentence_id=0, action="discard")]
    )
    assert overridden.manual_overrides[0].action == "discard"
    with pytest.raises(InvalidOverrideError):
        apply_overrides(state, [ManualOverride(sentence_id=4, action="discard")])
    with pytest.raises(WordOverridesNotSupportedError):
        apply_overrides(
            state,
            [ManualOverride(sentence_id=0, word_index=0, action="discard")],
        )

    configured = apply_module_config(state, "zooms", {"punch_in_scale": 1.2})
    assert configured.modules_config.zooms.punch_in_scale == 1.2
    with pytest.raises(ValidationError):
        apply_module_config(state, "zooms", {"punch_in_scale": 2.0})
    with pytest.raises(UnknownModuleError):
        apply_module_config(state, "nope", {})

    disabled = apply_module_enabled(state, "zooms", False)
    assert disabled.module_enabled.zooms is False
    with pytest.raises(UnknownModuleError):
        apply_module_enabled(state, "nope", False)

    preset = load_shipped_presets()[1]
    applied = apply_preset(state, preset)
    assert applied.modules_config == preset.modules_config
    assert applied.module_enabled == preset.module_enabled


def test_run_options_follow_config_and_enabled_flags(
    store: ProjectStore, tmp_path: Path
) -> None:
    record, state = store.create(tmp_path / "project")
    state = apply_media(state, media(tmp_path))
    state = state.model_copy(
        update={
            "transcript": [Sentence(id=0, start_sample=0, end_sample=10, text="x")],
            "manual_overrides": [ManualOverride(sentence_id=0, action="keep")],
        }
    )
    state = apply_module_enabled(state, "jl_cuts", False)
    state = apply_module_enabled(state, "zooms", False)
    state = apply_module_enabled(state, "export", False)
    options = store.run_options(record, state)
    assert options["jcut"] is False
    assert options["lcut"] is False
    assert options["zooms"] is False
    assert options["zoom_mode"] == "manual_rules"
    assert options["export_targets"] == []
    assert options["transcript_state"] == str(record.state_path)
    assert options["cull_retakes"] is True
    assert options["transcribe"] is False
    assert options["revision"] == state.revision + 1


def test_operator_presets_are_partial_and_shadow_shipped(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    entry = save_preset(
        "operator-test",
        {
            "description": "Operator preset.",
            "modules_config": {"zooms": {"punch_in_scale": 1.25}},
        },
    )
    assert entry.source == "operator"
    assert entry.preset.modules_config.zooms.punch_in_scale == 1.25
    assert entry.preset.modules_config.vad.min_silence_duration_ms == 400
    assert get_preset("operator-test").source == "operator"

    shadow = save_preset(
        "youtube-talking-head",
        {"description": "Shadow the shipped preset."},
    )
    assert shadow.source == "operator"
    assert get_preset("youtube-talking-head").source == "operator"
    assert "lecture-clean" in {item.preset.name for item in load_presets()}

    with pytest.raises(InvalidPresetNameError):
        validate_preset_name("../escape")
    with pytest.raises(PresetNotFoundError):
        get_preset("missing")
    with pytest.raises(PresetError):
        save_preset("bad-config", {"description": "x", "modules_config": "nope"})


def test_invalid_operator_preset_file_is_reported(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    directory = tmp_path / "home" / "presets"
    directory.mkdir(parents=True)
    (directory / "broken.json").write_text("{", encoding="utf-8")
    with pytest.raises(PresetError):
        load_presets()
