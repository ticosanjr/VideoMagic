"""Atomic beatmap application: cuts, overlays, zooms, and conflicts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application.beatmap import BeatmapError, apply_beatmap
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    OverlayClip,
    ProjectState,
    VideoSegment,
)


def _state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    return ProjectState(
        media_info=media,
        video_segments=[
            VideoSegment(
                clip_id="c1",
                source_in_frame=0,
                source_out_frame=60,
                timeline_in_frame=0,
                timeline_out_frame=60,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="c1",
                source_in_sample=0,
                source_out_sample=96000,
                timeline_in_sample=0,
                timeline_out_sample=96000,
            )
        ],
    )


def test_apply_cuts_ripples_video_and_audio(tmp_path: Path) -> None:
    state = _state(tmp_path)

    updated, report, _ = apply_beatmap(
        state,
        tmp_path,
        {"revision": 1, "keep_ranges": [{"start_sec": 10/30, "end_sec": 40/30}]},
        apply_cuts=True,
    )

    assert report.ok is True
    assert report.cuts == 1
    clip = updated.video_segments[0]
    assert (clip.source_in_frame, clip.source_out_frame) == (10, 40)
    assert (clip.timeline_in_frame, clip.timeline_out_frame) == (0, 30)
    audio = updated.audio_segments[0]
    assert audio.timeline_out_sample - audio.timeline_in_sample == 48000


def test_beatmap_adds_broll_overlay_and_zoom(tmp_path: Path) -> None:
    state = _state(tmp_path)
    asset = tmp_path / "assets" / "broll" / "x.mp4"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"clip")

    updated, report, sidecar = apply_beatmap(
        state,
        tmp_path,
        {
            "revision": 1,
            "broll": [
                {
                    "path": "assets/broll/x.mp4",
                    "start_frame": 0,
                    "duration_frames": 20,
                }
            ],
            "zoom_keyframes": [
                {
                    "clip_id": "c1",
                    "keyframes": [{"at": 0.0, "scale": 1.2}, {"at": 1.0, "scale": 1.5}],
                }
            ],
            "sfx_events": [{"path": "assets/broll/x.mp4", "start_frame": 0, "duration_frames": 10}],
        },
    )

    assert report.ok is True
    assert report.overlays == 1
    assert report.zooms == 1
    assert report.sfx_events == 1
    overlay = updated.overlays[0]
    assert overlay.kind == "video"
    assert overlay.width_ratio == 1.0
    assert [item.scale for item in updated.video_segments[0].transform.keyframes] == [1.2, 1.5]
    assert sidecar["sfx_events"][0]["start_frame"] == 0


def test_beatmap_rejects_revision_conflict(tmp_path: Path) -> None:
    state = _state(tmp_path)

    with pytest.raises(BeatmapError) as info:
        apply_beatmap(state, tmp_path, {"revision": 99})

    assert "revision conflict" in str(info.value)
    assert info.value.report.ok is False


def test_beatmap_rejects_missing_asset(tmp_path: Path) -> None:
    state = _state(tmp_path)

    with pytest.raises(BeatmapError) as info:
        apply_beatmap(
            state,
            tmp_path,
            {
                "broll": [
                    {"path": "assets/broll/missing.mp4", "start_frame": 0, "duration_frames": 5}
                ]
            },
        )

    assert any("missing asset" in item for item in info.value.report.conflicts)


def test_beatmap_rejects_invalid_range(tmp_path: Path) -> None:
    state = _state(tmp_path)

    with pytest.raises(ValueError):
        apply_beatmap(
            state,
            tmp_path,
            {"keep_ranges": [{"start_sec": 1.0, "end_sec": 0.5}]},
            apply_cuts=True,
        )


def test_beatmap_keeps_existing_overlays(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.overlays.append(
        OverlayClip(
            overlay_id="existing",
            path=str(tmp_path / "logo.png"),
            start_frame=0,
            duration_frames=10,
        )
    )

    updated, report, _ = apply_beatmap(state, tmp_path, {})

    assert report.ok is True
    assert updated.overlays[0].overlay_id == "existing"


def test_beatmap_rejects_invalid_cut_and_unknown_zoom(tmp_path: Path) -> None:
    state = _state(tmp_path)
    with pytest.raises(ValueError):
        apply_beatmap(
            state,
            tmp_path,
            {"keep_ranges": [{"start_sec": 1.0, "end_sec": 1.0}]},
            apply_cuts=True,
        )
    with pytest.raises(BeatmapError) as info:
        apply_beatmap(
            state,
            tmp_path,
            {"zoom_keyframes": [{"clip_id": "missing", "keyframes": []}]},
        )
    assert "unknown clip for zoom" in str(info.value)


def test_beatmap_rejects_cut_past_timeline_and_no_media(tmp_path: Path) -> None:
    state = _state(tmp_path)
    with pytest.raises(BeatmapError) as info:
        apply_beatmap(
            state,
            tmp_path,
            {"keep_ranges": [{"start_sec": 0.0, "end_sec": 99.0}]},
            apply_cuts=True,
        )
    assert any("exceeds timeline" in item for item in info.value.report.conflicts)

    empty = ProjectState()
    with pytest.raises(BeatmapError) as info:
        apply_beatmap(empty, tmp_path, {})
    assert "no media" in str(info.value)


def test_beatmap_rejects_missing_sfx_and_blocked_asset(tmp_path: Path) -> None:
    state = _state(tmp_path)
    with pytest.raises(BeatmapError) as info:
        apply_beatmap(
            state,
            tmp_path,
            {"sfx_events": [{"path": "missing.wav", "start_frame": 0}]},
        )
    assert any("missing asset" in item for item in info.value.report.conflicts)

    asset = tmp_path / "assets" / "music" / "bed.wav"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"wav")
    licenses = tmp_path / "assets" / "licenses.json"
    licenses.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "title": "assets/music/bed.wav",
                        "path": "assets/music/bed.wav",
                        "license_status": "unknown",
                        "license": "unknown",
                        "page_url": "",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BeatmapError) as info:
        apply_beatmap(
            state,
            tmp_path,
            {"music_tracks": [{"path": "assets/music/bed.wav", "start_frame": 0}]},
        )
    assert any("license-blocked" in item for item in info.value.report.conflicts)


def test_beatmap_music_sidecar_and_writer(tmp_path: Path) -> None:
    from videoflow.application.beatmap import write_beatmap_sidecar

    state = _state(tmp_path)
    music = tmp_path / "music.wav"
    music.write_bytes(b"wav")

    updated, report, sidecar = apply_beatmap(
        state,
        tmp_path,
        {
            "music_tracks": [
                {
                    "path": "music.wav",
                    "start_frame": 0,
                    "end_frame": 60,
                    "gain_db": -18.0,
                    "duck_under_speech": True,
                }
            ]
        },
    )

    assert report.music_tracks == 1
    assert sidecar["music_tracks"][0]["end_frame"] == 60
    path = write_beatmap_sidecar(tmp_path, sidecar)
    assert path.is_file()
    assert updated.video_segments


def test_beatmap_v2_transitions_graphics_and_captions(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.video_segments.append(
        VideoSegment(
            clip_id="c2",
            source_in_frame=0,
            source_out_frame=30,
            timeline_in_frame=60,
            timeline_out_frame=90,
        )
    )
    state.audio_segments.append(
        AudioSegment(
            clip_id="c2",
            source_in_sample=0,
            source_out_sample=48000,
            timeline_in_sample=96000,
            timeline_out_sample=144000,
        )
    )
    graphic = tmp_path / "assets" / "graphics" / "card.mov"
    graphic.parent.mkdir(parents=True)
    graphic.write_bytes(b"graphic")
    sfx = tmp_path / "assets" / "sfx" / "whoosh.wav"
    sfx.parent.mkdir(parents=True)
    sfx.write_bytes(b"sfx")

    updated, report, sidecar = apply_beatmap(
        state,
        tmp_path,
        {
            "transitions": [
                {
                    "clip_id": "c1",
                    "type": "wipe_left",
                    "duration_frames": 8,
                    "linked_sfx": str(sfx),
                }
            ],
            "graphics": [
                {
                    "path": str(graphic),
                    "start_frame": 10,
                    "duration_frames": 20,
                    "engine": "hyperframes",
                }
            ],
            "captions": [{"text": "primeira frase", "start_frame": 0, "end_frame": 30}],
        },
    )

    assert report.transitions == 1
    assert report.graphics == 1
    assert report.captions == 1
    transition = updated.video_segments[0].transition_out
    assert transition is not None and transition.type == "wipe_left"
    assert any(item.path.endswith("card.mov") for item in updated.overlays)
    assert (tmp_path / "captions" / "beatmap.ass").is_file()
    assert (tmp_path / "subtitles.ass").is_file()
    assert sidecar["schema_version"] == 2
    assert sidecar["sfx_events"][0]["linked_transition"] == "wipe_left"
