from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.contract.test_exporters import sample_state
from videoflow.domain.state import InactiveSegment
from videoflow.exporters.fcpxml import export_fcpxml
from videoflow.exporters.kdenlive import export_kdenlive
from videoflow.exporters.xmeml import export_xmeml


def _with_quarantine(tmp_path: Path):
    state = sample_state(tmp_path)
    video = state.video_segments[0].model_copy(
        update={
            "clip_id": "q1",
            "source_in_frame": 30,
            "source_out_frame": 60,
        }
    )
    audio = state.audio_segments[0].model_copy(
        update={
            "clip_id": "q1",
            "source_in_sample": 48000,
            "source_out_sample": 96000,
        }
    )
    state.inactive_segments = [
        InactiveSegment(
            clip_id="q1",
            reason="retake",
            video=video,
            audio=audio,
        )
    ]
    return state


def test_fcpxml_quarantine_lane_is_labelled_v2_a2(tmp_path: Path) -> None:
    output = export_fcpxml(_with_quarantine(tmp_path), tmp_path / "timeline.fcpxml")
    root = ET.parse(output).getroot()

    clips = [
        item
        for item in root.findall(".//spine/asset-clip")
        if item.attrib.get("lane") == "1"
    ]
    assert any((item.attrib.get("name") or "") == "Quarantine V2/A2 q1 (retake)" for item in clips)
    markers = [
        item
        for item in root.findall(".//spine/asset-clip/marker")
        if "Quarantine V2/A2" in (item.attrib.get("note") or "")
    ]
    assert len(markers) == 1


def test_xmeml_quarantine_is_a_disabled_track_with_marker(tmp_path: Path) -> None:
    output = export_xmeml(_with_quarantine(tmp_path), tmp_path / "timeline.xml")
    root = ET.parse(output).getroot()

    tracks = root.findall("./sequence/media/video/track")
    quarantine = [
        track
        for track in tracks
        if any(
            "Quarantine V2/A2" in (item.findtext("name") or "")
            for item in track.findall("clipitem")
        )
    ]
    assert len(quarantine) == 1
    assert quarantine[0].findtext("enabled") == "FALSE"
    assert quarantine[0].find("clipitem/enabled").text == "FALSE"

    markers = [
        marker
        for marker in root.findall("./sequence/marker")
        if marker.findtext("name") == "Quarantine V2/A2"
    ]
    assert len(markers) == 1
    assert "q1: retake" in (markers[0].findtext("comment") or "")


def test_kdenlive_quarantine_is_a_native_guide(tmp_path: Path) -> None:
    output = export_kdenlive(_with_quarantine(tmp_path), tmp_path / "timeline.kdenlive")
    root = ET.parse(output).getroot()

    guides = root.find(
        "./playlist[@id='main_bin']/property[@name='kdenlive:docproperties.guides']"
    )
    assert guides is not None
    payload = json.loads(guides.text or "[]")
    quarantine = [
        item for item in payload if "Quarantine V2/A2" in item.get("comment", "")
    ]
    assert len(quarantine) == 1
    assert "retake" in quarantine[0]["comment"]
    assert quarantine[0]["pos"] == 30
