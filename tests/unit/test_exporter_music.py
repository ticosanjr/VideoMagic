"""Music beds and ducking envelopes reach every NLE writer."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from tests.contract.test_exporters import sample_state
from videoflow.exporters.extras import NleAdjustment, NleExtras, NleMusic
from videoflow.exporters.fcpxml import _seconds, export_fcpxml
from videoflow.exporters.xmeml import export_xmeml


def _extras() -> NleExtras:
    return NleExtras(
        music=(
            NleMusic(
                path="/music/bed.wav",
                start_sec=1.0,
                duration_sec=4.0,
                gain_db=-18.0,
                duck_ranges=((1.5, 2.5, -12.0), (3.0, 3.4, -8.0)),
            ),
        ),
        adjustments=(
            NleAdjustment(
                name="Finishing",
                start_sec=0.0,
                end_sec=10.0,
                lut_path="/luts/look.cube",
                grain_amount=0.2,
                grain_fps=12.0,
            ),
        ),
    )


def test_xmeml_music_track_with_ducking(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    target = export_xmeml(state, tmp_path / "timeline.xml", extras=_extras())

    root = ET.parse(target).getroot()
    tracks = root.findall("./sequence/media/audio/track")
    assert any(track.findtext("clipitem[@id='music-1']/name") == "bed" for track in tracks)
    levels = root.findall(".//effect[effectid='audiolevels']/parameter/keyframe")
    assert len(levels) >= 5
    whens = [int(item.findtext("when") or 0) for item in levels]
    assert whens == sorted(whens)


def test_fcpxml_music_lane_and_ducking(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    target = export_fcpxml(state, tmp_path / "timeline.fcpxml", extras=_extras())

    root = ET.parse(target).getroot()
    music = root.findall("./library/event/project/sequence/spine/asset-clip[@lane='5']")
    assert len(music) == 1
    assert music[0].attrib["audioRole"] == "music"
    keyframes = music[0].findall(".//adjust-volume/param/keyframeAnimation/keyframe")
    assert len(keyframes) >= 6
    assert any(item.attrib["value"].endswith("dB") for item in keyframes)
    assert root.findall(".//filter-video")


def test_fcpxml_seconds_helper_and_duplicate_times() -> None:
    assert _seconds(0.0).numerator == 0
    assert float(_seconds(1.5)) == 1.5

    state_extras = NleExtras(
        music=(
            NleMusic(
                path="/m.wav", start_sec=0.0, duration_sec=1.0, duck_ranges=((0.0, 1.0, 0.0),)
            ),
        )
    )
    assert state_extras.music[0].duck_ranges
