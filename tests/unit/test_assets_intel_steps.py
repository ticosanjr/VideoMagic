"""Asset intelligence steps: shots, matching, beats, and SFX planning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit.test_steps_coverage_extra import (
    make_clip,
    make_context,
    make_media,
    sentence,
)
from videoflow.application.shorts import ShortClip
from videoflow.steps import assets_intel
from videoflow.steps.assets_intel import (
    AssetMatchStep,
    BeatParams,
    MatchParams,
    MusicBeatStep,
    SfxParams,
    SfxPlanStep,
    ShotsParams,
    ShotsStep,
    _overlap,
    _tfidf_scores,
)
from videoflow.steps.base import StepIO

RATE = 48000


def test_term_overlap_ignores_short_words() -> None:
    assert _overlap("", "") == 0.0
    assert _overlap("the cat", "the cat") == 0.0
    assert _overlap("podcast interview", "interview podcast") == 1.0


def test_tfidf_prefers_the_matching_document() -> None:
    scores = _tfidf_scores("ocean waves", ["ocean waves clip", "city traffic"])

    assert scores[0] > scores[1]


def test_shots_step_writes_thumbnails_and_warns_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = make_context(tmp_path, media_info=make_media(tmp_path))
    monkeypatch.setattr(assets_intel, "detect_scene_changes", lambda *_a, **_k: [0.0, 1.0])
    monkeypatch.setattr(
        assets_intel, "scene_intervals", lambda *_a, **_k: [(0, RATE), (RATE, 2 * RATE)]
    )
    calls: list[str] = []

    class Adapter:
        def render_thumbnail(self, _source: Path, target: Path, *, time_sec: float) -> None:
            calls.append(str(target))
            if target.name.endswith("2.png"):
                raise RuntimeError("decoder failed")
            target.write_bytes(b"png")

    monkeypatch.setattr(assets_intel, "FFmpegAdapter", Adapter)
    io = StepIO(progress=lambda *_a: None)

    ShotsStep().run(context, ShotsParams(), io)

    payload = json.loads((context.output / "shots" / "shots.json").read_text(encoding="utf-8"))
    assert [shot["id"] for shot in payload["shots"]] == ["shot-1", "shot-2"]
    assert payload["shots"][0]["thumbnail"].endswith("shot-1.png")
    assert "thumbnail" not in payload["shots"][1]
    assert any("Shot thumbnail failed" in warning for warning in context.warnings)
    assert context.metadata["scenes"] == payload["shots"]
    assert ShotsStep().cache_outputs(context) == (context.output / "shots" / "shots.json",)
    assert len(calls) == 2


def test_shots_step_falls_back_to_one_whole_clip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = make_context(tmp_path, media_info=make_media(tmp_path))
    monkeypatch.setattr(assets_intel, "detect_scene_changes", lambda *_a, **_k: [])
    monkeypatch.setattr(assets_intel, "scene_intervals", lambda *_a, **_k: [])

    ShotsStep().run(context, ShotsParams(thumbnails=False), StepIO())

    [shot] = context.metadata["scenes"]
    assert shot["start_sample"] == 0
    assert shot["end_sample"] == context.duration_samples()
    assert "thumbnail" not in shot


def test_asset_match_uses_tfidf_without_embeddings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = make_clip("Ocean story", start=0, end=4 * RATE)
    context = make_context(
        tmp_path,
        media_info=make_media(tmp_path),
        selected_shorts=[clip],
        transcript=[sentence(0, 0, RATE, "waves and ocean")],
        metadata={"scenes": [{"id": "shot-1", "start_sample": 0, "end_sample": RATE}]},
    )
    assets = [
        {"id": "a", "name": "ocean waves", "path": "/a.mp4", "kind": "video", "tags": []},
        {"id": "b", "name": "city", "path": "/b.mp4", "kind": "video", "tags": []},
        {"id": "c", "name": "photo", "path": "/c.png", "kind": "image", "tags": []},
        {"id": "d", "name": "audio", "path": "/d.wav", "kind": "audio", "tags": []},
    ]
    monkeypatch.setattr(assets_intel, "list_assets", lambda limit=2000: assets)
    monkeypatch.setattr(assets_intel.embeddings, "available", lambda: False)

    AssetMatchStep().run(context, MatchParams(query="ocean"), StepIO())

    plan = context.metadata["broll_plan"]
    assert list(plan) == ["Ocean story"]
    assert plan["Ocean story"][0]["path"] == "/a.mp4"
    assert plan["Ocean story"][0]["shot_id"] == "shot-1"
    assert "broll_matches" in context.artifacts
    assert "broll_licenses" in context.artifacts


def test_asset_match_uses_embeddings_and_limits_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = make_clip("Story", start=0, end=4 * RATE)
    context = make_context(
        tmp_path,
        media_info=make_media(tmp_path),
        selected_shorts=[clip],
        metadata={
            "scenes": [
                {"id": "s1", "start_sample": 0, "end_sample": RATE},
                {"id": "s2", "start_sample": RATE, "end_sample": 2 * RATE},
            ]
        },
    )
    assets = [
        {"id": "a", "name": "a", "path": "/a.mp4", "kind": "video", "tags": []},
        {"id": "b", "name": "b", "path": "/b.mp4", "kind": "video", "tags": []},
    ]
    monkeypatch.setattr(assets_intel, "list_assets", lambda limit=2000: assets)
    monkeypatch.setattr(assets_intel.embeddings, "available", lambda: True)
    monkeypatch.setattr(assets_intel.embeddings, "scores", lambda *_a: [0.9, 0.8])

    AssetMatchStep().run(
        context, MatchParams(max_per_short=1, min_score=0.5), StepIO()
    )

    entries = context.metadata["broll_plan"]["Story"]
    assert len(entries) == 1
    assert entries[0]["path"] == "/a.mp4"
    assert entries[0]["shot_id"] == "s1"


def test_asset_match_deduplicates_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clips = [
        make_clip("One", start=0, end=2 * RATE),
        make_clip("Two", start=2 * RATE, end=4 * RATE),
    ]
    context = make_context(
        tmp_path,
        media_info=make_media(tmp_path),
        selected_shorts=clips,
    )
    assets = [{"id": "a", "name": "shared", "path": "/a.mp4", "kind": "video"}]
    monkeypatch.setattr(assets_intel, "list_assets", lambda limit=2000: assets)
    monkeypatch.setattr(assets_intel.embeddings, "available", lambda: False)

    AssetMatchStep().run(context, MatchParams(min_score=0.0), StepIO())

    assert context.metadata["broll_plan"]["One"]
    assert context.metadata["broll_plan"]["Two"] == []
    assert AssetMatchStep().cache_outputs(context)[0].name == "broll-matches.json"


def test_windows_clip_scene_bounds() -> None:
    clip = ShortClip("A", 10, 20, (0,), ((10, 20),))

    assert AssetMatchStep._windows(clip, []) == [(10, 20, "")]
    assert AssetMatchStep._windows(clip, [(0, 15, "s1"), (25, 30, "s2")]) == [
        (10, 15, "s1")
    ]


def test_music_beat_tempo_fallback_and_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = make_context(tmp_path, media_info=make_media(tmp_path))

    MusicBeatStep().run(context, BeatParams(tempo_bpm=120), StepIO())

    beats = context.metadata["beats"]
    assert beats[0] == 0.0
    assert beats[1] == 0.5
    assert beats[-1] < 4.0
    assert json.loads(Path(context.artifacts["beats"]).read_text())[ "source" ] == "tempo"

    monkeypatch.setattr(assets_intel, "detect_beats", lambda _path: [0.0, 0.5, 1.0])
    MusicBeatStep().run(context, BeatParams(path=str(tmp_path / "song.wav")), StepIO())
    payload = json.loads(Path(context.artifacts["beats"]).read_text())
    assert payload["source"] == "audio"
    assert payload["tempo_bpm"] == 120.0


def test_music_beat_detection_failure_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = make_context(tmp_path, media_info=make_media(tmp_path))

    def fail(_path: Path) -> list[float]:
        raise RuntimeError("no audio")

    monkeypatch.setattr(assets_intel, "detect_beats", fail)

    MusicBeatStep().run(context, BeatParams(path=str(tmp_path / "bad.wav")), StepIO())

    assert any("fell back to tempo" in warning for warning in context.warnings)
    assert context.metadata["beats"]
    assert MusicBeatStep().cache_outputs(context)[0].name == "beats.json"


def test_sfx_plan_uses_the_default_folder(tmp_path: Path) -> None:
    context = make_context(tmp_path, media_info=make_media(tmp_path))
    context.selected_shorts = [make_clip("One"), make_clip("Two")]
    sfx = context.output.parent / "sfx"
    sfx.mkdir(parents=True)
    (sfx / "a.wav").write_bytes(b"wav")
    (sfx / "b.mp3").write_bytes(b"mp3")

    SfxPlanStep().run(context, SfxParams(max_per_short=2), StepIO())

    plan = context.metadata["sfx_plan"]
    assert [Path(entry["path"]).name for entry in plan["One"]] == ["a.wav", "b.mp3"]
    assert [Path(entry["path"]).name for entry in plan["Two"]] == ["b.mp3", "a.wav"]
    assert SfxPlanStep().cache_outputs(context)[0].name == "plan.json"


def test_sfx_plan_without_files_or_content(tmp_path: Path) -> None:
    context = make_context(tmp_path, media_info=make_media(tmp_path))
    context.selected_shorts = [make_clip("One")]
    directory = tmp_path / "empty"
    directory.mkdir()

    SfxPlanStep().run(context, SfxParams(directory=str(directory)), StepIO())

    assert context.metadata["sfx_plan"] == {"One": []}
