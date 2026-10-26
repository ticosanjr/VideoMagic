"""Kdenlive export extras: B-roll, titles, stems, and transition guards."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from tests.contract.test_exporters import sample_state, transition_state
from videoflow.exporters.extras import NleBroll, NleExtras, NleMarker, NleTitle
from videoflow.exporters.kdenlive import export_kdenlive


def test_export_with_titles_broll_and_audio_stem(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    stem = tmp_path / "stem.wav"
    stem.write_bytes(b"wav")
    extras = NleExtras(
        markers=(NleMarker(name="Intro", start_sec=1.0),),
        titles=(NleTitle(text="Hello", start_sec=0.5, end_sec=2.0),),
        broll=(
            NleBroll(path="/broll.mp4", start_sec=1.0, duration_sec=1.0, name="B-roll"),
            NleBroll(
                path="/logo.png",
                start_sec=3.0,
                duration_sec=2.0,
                name="Logo",
                kind="image",
            ),
        ),
        color_filters=("lift_gamma_gain",),
        audio_stem=str(stem),
    )

    target = export_kdenlive(state, tmp_path / "timeline.kdenlive", extras=extras)

    root = ET.parse(target).getroot()
    producers = {item.get("id"): item for item in root.findall("producer")}
    assert "title0" in producers
    assert "broll0" in producers
    assert "broll1" in producers
    image_service = [
        prop.text
        for prop in producers["broll1"].findall("property")
        if prop.get("name") == "mlt_service"
    ]
    assert image_service == ["qimage"]
    assert root.find("./playlist[@id='playlist4']") is not None
    assert root.find("./playlist[@id='playlist5']") is not None


def test_export_without_extras_has_no_overlay_playlist(tmp_path: Path) -> None:
    state = sample_state(tmp_path)

    target = export_kdenlive(state, tmp_path / "timeline.kdenlive")

    root = ET.parse(target).getroot()
    assert root.find("./playlist[@id='playlist4']") is None
    assert root.find("./playlist[@id='playlist5']") is None


def test_long_crossfade_is_skipped_at_the_media_end(tmp_path: Path) -> None:
    state = transition_state(tmp_path, "crossfade")
    state.video_segments[0].transition_out.duration_frames = 120

    target = export_kdenlive(state, tmp_path / "timeline.kdenlive")

    root = ET.parse(target).getroot()
    assert root.tag == "mlt"
    assert root.find("./playlist[@id='playlist_v1']") is not None


def test_fade_to_black_is_exported(tmp_path: Path) -> None:
    state = transition_state(tmp_path, "fade_to_black")

    target = export_kdenlive(state, tmp_path / "timeline.kdenlive")

    root = ET.parse(target).getroot()
    levels = [
        prop.text
        for prop in root.findall(".//filter/property[@name='level']")
        if prop.text
    ]
    assert levels
