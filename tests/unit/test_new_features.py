from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.broll_approval import (
    load_approvals,
    ordered_entries,
    save_approval,
)
from videoflow.application.providers import (
    ProviderConfig,
    delete_provider,
    list_providers,
    load_providers,
    resolve_chain,
    set_default,
    upsert_provider,
)
from videoflow.application.timeline_edit import TimelineEdit, apply_timeline_edit
from videoflow.application.timeline_history import TimelineHistory
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment


def media() -> MediaInfo:
    return MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=100,
        fps_num=25,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )


def state_with_two_clips() -> ProjectState:
    return ProjectState(
        media_info=media(),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=25,
                timeline_in_frame=0,
                timeline_out_frame=25,
            ),
            VideoSegment(
                clip_id="v2",
                source_in_frame=25,
                source_out_frame=50,
                timeline_in_frame=25,
                timeline_out_frame=50,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            ),
            AudioSegment(
                clip_id="v2",
                source_in_sample=48000,
                source_out_sample=96000,
                timeline_in_sample=48000,
                timeline_out_sample=96000,
            ),
        ],
    )


def test_split_creates_two_adjacent_segments() -> None:
    state = state_with_two_clips()
    split = apply_timeline_edit(
        state, TimelineEdit(clip_id="v1", action="split", split_sec=0.5)
    )
    assert len(split.video_segments) == 3
    left, right = split.video_segments[0], split.video_segments[1]
    assert left.timeline_out_frame == right.timeline_in_frame == 12
    assert left.source_out_frame == right.source_in_frame
    assert right.clip_id != "v1"
    assert len(split.audio_segments) == 3


def test_ripple_delete_closes_the_gap() -> None:
    state = state_with_two_clips()
    result = apply_timeline_edit(state, TimelineEdit(clip_id="v1", action="ripple"))
    assert [clip.clip_id for clip in result.video_segments] == ["v2"]
    assert result.video_segments[0].timeline_in_frame == 0
    assert result.audio_segments[0].timeline_in_sample == 0


def test_delete_keeps_the_gap() -> None:
    state = state_with_two_clips()
    result = apply_timeline_edit(state, TimelineEdit(clip_id="v1", action="delete"))
    assert result.video_segments[0].timeline_in_frame == 25


def test_history_undo_and_redo(tmp_path: Path) -> None:
    history = TimelineHistory(tmp_path / "timeline_history.json")
    original = state_with_two_clips()
    edited = apply_timeline_edit(
        original.model_copy(deep=True), TimelineEdit(clip_id="v1", action="move", delta_sec=1.0)
    )
    history.record(original)
    assert history.can_undo and not history.can_redo
    restored = history.undo_state(edited)
    assert restored is not None
    assert restored.video_segments[0].timeline_in_frame == 0
    assert history.can_redo
    redone = history.redo_state(restored)
    assert redone is not None
    assert redone.video_segments[0].timeline_in_frame == 25
    assert edited.video_segments[0].timeline_in_frame == 25


def test_broll_approval_orders_only_approved_entries(tmp_path: Path) -> None:
    plan = {
        "Short one": [
            {"path": "/a.mp4"},
            {"path": "/b.mp4"},
            {"path": "/c.mp4"},
        ]
    }
    save_approval(tmp_path, title="Short one", approved=[0, 2], order=[2, 0], plan=plan)
    approvals = load_approvals(tmp_path)
    assert approvals["Short one"]["approved"] == [0, 2]
    ordered = ordered_entries(plan, approvals)
    assert [entry["path"] for entry in ordered["Short one"]] == ["/c.mp4", "/a.mp4"]
    assert (tmp_path / "broll_approval.json").is_file()


def test_provider_fallback_chain(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    upsert_provider(
        ProviderConfig(
            id="local-llm",
            name="Local",
            capability="llm",
            base_url="http://127.0.0.1:11434/v1",
            is_default=True,
            fallback=["remote-llm"],
        )
    )
    upsert_provider(
        ProviderConfig(
            id="remote-llm",
            name="Remote",
            capability="llm",
            base_url="https://api.example.com/v1",
            api_key_env="EXAMPLE_KEY",
        )
    )
    chain = resolve_chain("llm")
    assert [item["id"] for item in chain] == ["local-llm", "remote-llm"]
    assert len(load_providers()) == 2
    set_default("remote-llm")
    chain = resolve_chain("llm")
    assert chain[0]["id"] == "remote-llm"
    delete_provider("remote-llm")
    assert [item["id"] for item in list_providers()] == ["local-llm"]


def test_flow_conditional_and_subflow_execute(monkeypatch, tmp_path: Path) -> None:
    from videoflow.core.recipe import Recipe
    from videoflow.engine.runner import RecipeRunner

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "clip.mp4").write_bytes(b"x")

    recipe = Recipe.model_validate(
        {
            "schema_version": 1,
            "id": "flow_test",
            "name": "Flow test",
            "steps": [
                {
                    "id": "branch",
                    "type": "flow.conditional",
                    "params": {
                        "condition": "always",
                        "when_true": [
                            {
                                "type": "assets.index",
                                "params": {"asset_dir": str(assets)},
                            }
                        ],
                    },
                }
            ],
        }
    )
    result = RecipeRunner(recipe).run(source, tmp_path / "out", resume=False)
    payload = json.loads((tmp_path / "out" / "assets-index.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["assets"]
    assert result.to_dict()["mode"] == "recipe"


def test_flow_rejects_unknown_condition(monkeypatch, tmp_path: Path) -> None:
    from videoflow.core.recipe import Recipe
    from videoflow.domain.errors import StepExecutionError
    from videoflow.engine.runner import RecipeRunner

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = Recipe.model_validate(
        {
            "schema_version": 1,
            "id": "flow_test_bad",
            "name": "Flow test bad",
            "steps": [
                {
                    "id": "branch",
                    "type": "flow.conditional",
                    "params": {"condition": "not-a-condition"},
                }
            ],
        }
    )
    with pytest.raises(StepExecutionError):
        RecipeRunner(recipe).run(source, tmp_path / "out", resume=False)


def test_titles_plan_writes_lower_thirds_and_title_cards(tmp_path: Path) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.domain.state import Sentence
    from videoflow.steps.base import StepIO
    from videoflow.steps.content import TitlesParams, TitlesStep

    state = state_with_two_clips()
    state.transcript = [
        Sentence(id=0, start_sample=0, end_sample=48000, text="hello", speaker=0),
        Sentence(id=1, start_sample=48000, end_sample=96000, text="welcome", speaker=1),
    ]
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=state.media_info,
        state=state,
        shorts=[{"title": "First Short"}],
    )
    TitlesStep().run(
        context,
        TitlesParams(intro_title="Intro", outro_title="Outro"),
        StepIO(stage="titles"),
    )
    payload = json.loads((tmp_path / "out" / "titles.json").read_text(encoding="utf-8"))
    assert len(payload["lower_thirds"]) == 2
    assert [card["kind"] for card in payload["title_cards"]] == ["intro", "short", "outro"]


def test_subflow_step_runs_inline_steps(tmp_path: Path) -> None:
    from videoflow.core.recipe import Recipe
    from videoflow.engine.runner import RecipeRunner

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "clip.mp4").write_bytes(b"x")
    recipe = Recipe.model_validate(
        {
            "schema_version": 1,
            "id": "subflow_test",
            "name": "Subflow test",
            "steps": [
                {
                    "id": "group",
                    "type": "flow.subflow",
                    "params": {
                        "steps": [
                            {
                                "type": "assets.index",
                                "params": {"asset_dir": str(assets)},
                            }
                        ]
                    },
                }
            ],
        }
    )
    RecipeRunner(recipe).run(source, tmp_path / "out", resume=False)
    assert (tmp_path / "out" / "assets-index.json").is_file()
