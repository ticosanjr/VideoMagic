"""NLE finishing extras: titles, filters, B-roll, overlays, and chapters."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import nle_extras
from videoflow.application.nle_extras import _broll, _filters, _project_overlays, _seconds, _titles


def test_ass_time_parsing() -> None:
    assert _seconds("01:02:03.50") == pytest.approx(3723.5)
    assert _seconds("not a time") == 0.0


def test_titles_skip_malformed_and_empty_lines(tmp_path: Path) -> None:
    assert _titles(tmp_path / "missing.ass") == ()

    path = tmp_path / "titles.ass"
    path.write_text(
        "\n".join(
            [
                "[Events]",
                "Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,{\\b1}Hello world",
                "Dialogue: broken",
                "Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,{\\i1}",
            ]
        ),
        encoding="utf-8",
    )

    titles = _titles(path)

    assert len(titles) == 1
    assert titles[0].text == "Hello world"
    assert titles[0].start_sec == 1.0
    assert titles[0].end_sec == 2.5


def test_filters_read_json_and_ignore_errors(tmp_path: Path) -> None:
    assert _filters(tmp_path / "missing.json") == ()

    path = tmp_path / "filters.json"
    path.write_text('{"filters": ["eq=contrast=1.2", ""]}', encoding="utf-8")
    assert _filters(path) == ("eq=contrast=1.2",)

    path.write_text("not json", encoding="utf-8")
    assert _filters(path) == ()


def test_broll_prefers_matches_and_skips_bad_cues(tmp_path: Path) -> None:
    assert _broll(tmp_path) == ()

    (tmp_path / "broll-matches.json").write_text("not json", encoding="utf-8")
    assert _broll(tmp_path) == ()

    (tmp_path / "broll.json").write_text(
        json.dumps(
            {
                "shorts": {
                    "One": [
                        {"path": "/a.mp4", "start_sec": 1.5, "duration_sec": 3},
                        {"start_sec": 0},
                        "not a dict",
                    ],
                    "Two": "nope",
                }
            }
        ),
        encoding="utf-8",
    )

    entries = _broll(tmp_path)

    assert len(entries) == 1
    assert entries[0].path == "/a.mp4"
    assert entries[0].start_sec == 1.5
    assert entries[0].duration_sec == 3.0
    assert entries[0].name == "a"


def test_project_overlays_read_state(tmp_path: Path) -> None:
    assert _project_overlays(tmp_path) == ()

    (tmp_path / "project_state.json").write_text("not json", encoding="utf-8")
    assert _project_overlays(tmp_path) == ()

    (tmp_path / "project_state.json").write_text(
        json.dumps(
            {
                "media_info": {"fps_num": 25, "fps_den": 1},
                "overlays": [
                    {
                        "path": "/logo.png",
                        "start_frame": 25,
                        "duration_frames": 50,
                        "kind": "image",
                    },
                    {"path": ""},
                    "not a dict",
                ],
            }
        ),
        encoding="utf-8",
    )

    [overlay] = _project_overlays(tmp_path)

    assert overlay.path == "/logo.png"
    assert overlay.start_sec == 1.0
    assert overlay.duration_sec == 2.0
    assert overlay.kind == "image"


def test_nle_extras_merges_markers_and_chapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = SimpleNamespace(label="Intro", id="m1", time_sec=1.5, color="#ff0000")
    monkeypatch.setattr(
        nle_extras, "load_meta", lambda _directory: SimpleNamespace(markers=[marker])
    )
    (tmp_path / "chapters.json").write_text("not json", encoding="utf-8")

    extras = nle_extras.nle_extras_from_output(tmp_path)

    assert [item.name for item in extras.markers] == ["Intro"]

    (tmp_path / "chapters.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {"title": "Start", "start_sec": 0},
                    {"title": "No time"},
                    "not a dict",
                ]
            }
        ),
        encoding="utf-8",
    )

    extras = nle_extras.nle_extras_from_output(tmp_path)

    assert [item.name for item in extras.markers] == ["Start", "Intro"]
    assert extras.markers[0].note == "chapter"


def test_music_reads_beatmap_and_ducking(tmp_path: Path) -> None:
    (tmp_path / "project_state.json").write_text(
        json.dumps({"media_info": {"fps_num": 30, "fps_den": 1}}), encoding="utf-8"
    )
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "beatmap.json").write_text(
        json.dumps(
            {
                "music_tracks": [
                    {
                        "path": "/music/track.wav",
                        "start_frame": 30,
                        "end_frame": 120,
                        "gain_db": -20.0,
                        "duck_under_speech": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (audio / "ducking.json").write_text(
        json.dumps({"ducking": [{"start_sec": 2.0, "end_sec": 3.0, "level_db": -12.0}]}),
        encoding="utf-8",
    )

    tracks = nle_extras._music(tmp_path)

    assert len(tracks) == 1
    assert tracks[0].start_sec == 1.0
    assert tracks[0].duration_sec == 3.0
    assert tracks[0].gain_db == -20.0
    assert tracks[0].duck_ranges == ((2.0, 3.0, -12.0),)
