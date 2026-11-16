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
    levels = [prop.text for prop in root.findall(".//filter/property[@name='level']") if prop.text]
    assert levels


def test_multisource_export_creates_one_chain_per_source(tmp_path: Path) -> None:
    from videoflow.domain.state import (
        AudioSegment,
        MediaInfo,
        ProjectState,
        VideoSegment,
    )

    first = tmp_path / "cam-a.mp4"
    second = tmp_path / "cam-b.mp4"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    media_a = MediaInfo(
        source_path=str(first),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    media_b = media_a.model_copy(update={"source_path": str(second)})
    state = ProjectState(
        sources={"cam-a": media_a, "cam-b": media_b},
        primary_source_id="cam-a",
        video_segments=[
            VideoSegment(
                clip_id="c1",
                source_id="cam-a",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            ),
            VideoSegment(
                clip_id="c2",
                source_id="cam-b",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=30,
                timeline_out_frame=60,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="c1",
                source_id="cam-a",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            ),
            AudioSegment(
                clip_id="c2",
                source_id="cam-b",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=48000,
                timeline_out_sample=96000,
            ),
        ],
    )

    target = export_kdenlive(state, tmp_path / "timeline.kdenlive")

    root = ET.parse(target).getroot()
    chains = {item.get("id"): item for item in root.findall("chain")}
    assert set(chains) == {"chain0", "chain1"}
    resources = {
        chain_id: [
            prop.text for prop in node.findall("property") if prop.get("name") == "resource"
        ][0]
        for chain_id, node in chains.items()
    }
    assert resources["chain0"].endswith("cam-a.mp4")
    assert resources["chain1"].endswith("cam-b.mp4")
    producers = {
        entry.get("producer")
        for playlist in ("playlist_v1", "playlist_v2", "playlist2")
        for entry in root.findall(f"./playlist[@id='{playlist}']/entry")
    }
    assert producers == {"chain0", "chain1"}


def test_music_playlist_carries_ducking_envelope(tmp_path: Path) -> None:
    from videoflow.exporters.extras import NleMusic

    state = sample_state(tmp_path)
    extras = NleExtras(
        music=(
            NleMusic(
                path="/music/bed.wav",
                start_sec=0.0,
                duration_sec=2.0,
                gain_db=-18.0,
                duck_ranges=((0.5, 1.5, -12.0),),
            ),
        )
    )

    target = export_kdenlive(state, tmp_path / "timeline.kdenlive", extras=extras)

    root = ET.parse(target).getroot()
    assert root.find("./playlist[@id='playlist_music']") is not None
    levels = [
        prop.text
        for prop in root.findall(".//playlist[@id='playlist_music']/entry/filter/property")
        if prop.get("name") == "level"
    ]
    assert levels and "-30" in levels[0]
