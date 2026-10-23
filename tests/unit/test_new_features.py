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


def test_flow_loop_isolates_each_file(tmp_path: Path) -> None:
    from videoflow.core.recipe import Recipe
    from videoflow.engine.runner import RecipeRunner

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.mp4").write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "clip.mp4").write_bytes(b"x")
    recipe = Recipe.model_validate(
        {
            "schema_version": 1,
            "id": "loop_test",
            "name": "Loop test",
            "steps": [
                {
                    "id": "each",
                    "type": "flow.loop",
                    "params": {
                        "over": "files",
                        "glob": "*.mp4",
                        "steps": [
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
    loop_runs = result.context.metadata.get("loop_runs", [])
    assert len(loop_runs) == 2
    assert all(Path(item["output"]).is_dir() for item in loop_runs)
    assert any(key.endswith("assets_index") for key in result.context.artifacts)


def test_titles_ass_contains_title_and_lower_third(tmp_path: Path) -> None:
    from videoflow.application.titles import render_titles_ass

    target = render_titles_ass(
        {
            "title_cards": [
                {"kind": "intro", "start_sec": 0.0, "duration_sec": 2.0, "text": "Intro"}
            ],
            "lower_thirds": [
                {"start_sec": 1.0, "end_sec": 3.0, "text": "Speaker 1"}
            ],
        },
        tmp_path / "titles.ass",
        width=1920,
        height=1080,
    )
    text = target.read_text(encoding="utf-8")
    assert "PlayResX: 1920" in text
    assert "Intro" in text
    assert "Speaker 1" in text
    assert text.count("Dialogue:") == 2


def test_model_download_manager_persists_status(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import model_downloads

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    calls: list[str] = []

    def fake_install(model_id, **kwargs):
        calls.append(model_id)
        progress = kwargs.get("progress")
        if progress:
            progress(50, "half")
            progress(100, "done")
        return {"id": model_id, "installed": True, "path": str(tmp_path)}

    monkeypatch.setattr(model_downloads, "install_model", fake_install)
    manager = model_downloads.ModelDownloadManager()
    manager.start("faster-whisper-small")
    for _ in range(100):
        item = manager.get("faster-whisper-small")
        if item is not None and item.status == "installed":
            break
        import time

        time.sleep(0.01)
    assert calls == ["faster-whisper-small"]
    assert manager.get("faster-whisper-small").status == "installed"  # type: ignore[union-attr]
    assert (tmp_path / "model-downloads.json").is_file()
    reloaded = model_downloads.ModelDownloadManager()
    assert reloaded.get("faster-whisper-small").status == "installed"  # type: ignore[union-attr]


def test_review_and_thumbnail_deliverables(tmp_path: Path) -> None:
    from videoflow.application.deliverables import (
        approve_review,
        list_thumbnails,
        review_payload,
        select_thumbnail,
    )

    (tmp_path / "review.json").write_text('{"checks": [{"id": "timeline", "ok": true}]}')
    thumbs = tmp_path / "thumbnails"
    thumbs.mkdir()
    (thumbs / "thumbnail-1.png").write_bytes(b"png")
    (thumbs / "thumbnail-2.png").write_bytes(b"png")
    approve_review(tmp_path, approved=True, comment="ok", reviewer="qa")
    payload = review_payload(tmp_path)
    assert payload["approval"]["approved"] is True
    listing = list_thumbnails(tmp_path)
    assert listing["variants"] == ["thumbnail-1.png", "thumbnail-2.png"]
    select_thumbnail(tmp_path, "thumbnail-2.png")
    assert list_thumbnails(tmp_path)["selected"] == "thumbnail-2.png"


def test_export_mp4_applies_audio_color_and_title_filters(tmp_path: Path) -> None:
    from videoflow.exporters.mp4 import export_mp4

    captured: list[list[str]] = []

    class FakeAdapter:
        def render(self, args):
            captured.append(list(args))
            destination = Path(args[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"mp4")
            return destination

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    state = state_with_two_clips()
    assert state.media_info is not None
    state.media_info = state.media_info.model_copy(update={"source_path": str(source)})
    destination = export_mp4(
        state,
        tmp_path / "render.mp4",
        adapter=FakeAdapter(),
        audio_filters=["loudnorm=I=-16:TP=-1.5:LRA=11"],
        video_filters=["eq=contrast=1.1"],
        ass_path=tmp_path / "titles.ass",
    )
    assert destination.is_file()
    graph = captured[0][captured[0].index("-filter_complex") + 1]
    assert "[aout]loudnorm" in graph
    assert "[vout]eq=contrast=1.1[vcolor]" in graph
    assert "ass=" in graph
