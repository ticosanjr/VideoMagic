import xml.etree.ElementTree as ET
from pathlib import Path

import opentimelineio as otio
import pytest

from videoflow.application.export_service import export_timeline
from videoflow.application.timeline_builder import build_timeline
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.errors import ExportError
from videoflow.domain.state import MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.fcpxml import export_fcpxml
from videoflow.exporters.kdenlive import export_kdenlive
from videoflow.exporters.mp4 import export_mp4
from videoflow.exporters.otio_export import export_otio
from videoflow.exporters.xmeml import export_xmeml


def sample_state(tmp_path: Path) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    built = build_timeline(
        media,
        [(0, 48000), (96000, 144000)],
        jl=JlCutsConfig(enable_j_cuts=True, offset_ms=200),
        zooms=ZoomsConfig(mode="alternate_cuts"),
    )
    return ProjectState(
        media_info=media,
        video_segments=list(built.video_segments),
        audio_segments=list(built.audio_segments),
    )


def test_fcpxml_export_uses_audio_offset_and_transform(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    output = export_fcpxml(state, tmp_path / "timeline.fcpxml")
    root = ET.parse(output).getroot()
    assert root.tag == "fcpxml"
    assert root.attrib["version"] == "1.9"
    asset = root.find("./resources/asset")
    assert asset is not None
    assert asset.find("media-rep") is not None
    assert asset.attrib.get("src") is None
    assert asset.attrib["videoSources"] == "1"
    sequence = root.find(".//sequence")
    assert sequence is not None
    assert sequence.attrib["audioLayout"] == "mono"
    clips = root.findall(".//spine/asset-clip")
    assert len(clips) == 2
    first, second = clips
    assert first.attrib["start"] != second.attrib["audioStart"]
    assert first.attrib["srcEnable"] == "all"
    assert "adjust-transform" in [child.tag for child in second]


def test_fcpxml_supports_the_newer_dialect(tmp_path: Path) -> None:
    output = export_fcpxml(sample_state(tmp_path), tmp_path / "timeline.fcpxml", dialect="1.10")
    assert ET.parse(output).getroot().attrib["version"] == "1.10"


def test_xmeml_export_has_separate_video_and_audio_tracks(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    output = export_xmeml(state, tmp_path / "timeline.xml")
    root = ET.parse(output).getroot()
    assert root.tag == "xmeml"
    assert root.attrib["version"] == "4"
    sequence = root.find("./sequence")
    assert sequence is not None
    assert sequence.attrib["explodedTracks"] == "true"
    assert sequence.find("uuid") is not None
    video_items = root.findall("./sequence/media/video/track/clipitem")
    audio_items = root.findall("./sequence/media/audio/track/clipitem")
    assert len(video_items) == 2
    assert len(audio_items) == 2
    assert video_items[0].findtext("start") == "0"
    assert audio_items[1].findtext("start") != video_items[1].findtext("start")
    assert video_items[1].find("filter/effect/parameter/value") is not None
    for item in (*video_items, *audio_items):
        file_element = item.find("file")
        assert file_element is not None
        assert file_element.findtext("pathurl", "").startswith("file://localhost/")
        assert file_element.findtext("name")
    assert len(video_items[0].findall("link")) == 2
    assert len(audio_items[0].findall("link")) == 2


def test_kdenlive_export_is_a_native_mlt_project(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    output = export_kdenlive(state, tmp_path / "timeline.kdenlive")
    root = ET.parse(output).getroot()
    assert root.tag == "mlt"
    assert root.attrib["producer"] == "main_bin"
    profile = root.find("profile")
    assert profile is not None
    assert profile.attrib["width"] == "1920"
    assert profile.attrib["frame_rate_num"] == "30"
    chain = root.find("./chain[@id='chain0']")
    assert chain is not None
    resource = chain.find("property[@name='resource']")
    assert resource is not None and resource.text
    assert len(root.findall("./playlist[@id='playlist0']/entry")) == 2
    assert len(root.findall("./playlist[@id='playlist2']/entry")) == 2
    sequence = next(
        tractor
        for tractor in root.findall("tractor")
        if tractor.find("property[@name='kdenlive:clipname']") is not None
    )
    assert sequence.find("property[@name='kdenlive:uuid']") is not None
    final = root.find("./tractor[@id='final_tractor']")
    assert final is not None
    project_flag = final.find("property[@name='kdenlive:projectTractor']")
    assert project_flag is not None and project_flag.text == "1"


def test_otio_export_has_two_tracks(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    output = export_otio(state, tmp_path / "timeline.otio")
    timeline = otio.adapters.read_from_file(str(output))
    assert len(timeline.tracks) == 2
    assert timeline.tracks[0].kind == otio.schema.TrackKind.Video
    assert timeline.tracks[1].kind == otio.schema.TrackKind.Audio
    assert len(timeline.tracks[0]) == 2
    assert len(timeline.tracks[1]) == 2


def test_export_service_writes_all_three_targets(tmp_path: Path) -> None:
    artifacts = export_timeline(sample_state(tmp_path), tmp_path / "exports")
    assert set(artifacts) == {"resolve", "premiere", "kdenlive"}
    assert artifacts["resolve"].suffix == ".fcpxml"
    assert artifacts["premiere"].suffix == ".xml"
    assert artifacts["kdenlive"].suffix == ".kdenlive"
    assert all(path.exists() for path in artifacts.values())
    assert ET.parse(artifacts["premiere"]).getroot().tag == "xmeml"
    assert ET.parse(artifacts["kdenlive"]).getroot().tag == "mlt"


def test_export_service_rejects_an_unknown_target(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="Unknown export target"):
        export_timeline(sample_state(tmp_path), tmp_path / "exports", targets=("avid",))


def test_export_rejects_an_empty_timeline(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    with pytest.raises(ExportError):
        export_fcpxml(ProjectState(media_info=media), tmp_path / "out.fcpxml")


def test_export_rejects_offline_media(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    state.media_info.source_path = str(tmp_path / "gone.mp4")  # type: ignore[union-attr]
    with pytest.raises(ExportError, match="offline"):
        export_fcpxml(state, tmp_path / "out.fcpxml")


def test_export_rejects_missing_audio(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    state.audio_segments = []
    with pytest.raises(ExportError, match="mismatch"):
        export_xmeml(state, tmp_path / "out.xml")


def test_export_rejects_unpacked_video(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    first = state.video_segments[0]
    state.video_segments = [
        first,
        VideoSegment(
            clip_id="c2",
            source_in_frame=60,
            source_out_frame=90,
            timeline_in_frame=40,
            timeline_out_frame=70,
        ),
    ]
    with pytest.raises(ExportError, match="not packed"):
        export_otio(state, tmp_path / "out.otio")


@pytest.mark.xfail(reason="AC-01: NLE transitions land with the compatibility spike", strict=True)
def test_every_join_contains_a_fade(tmp_path: Path) -> None:
    raise AssertionError("audio transitions are not emitted yet")


@pytest.mark.xfail(reason="Direct render lands with the shorts pass", strict=True)
def test_mp4_export_writes_a_file(tmp_path: Path) -> None:
    output = export_mp4(sample_state(tmp_path), tmp_path / "preview.mp4")
    assert output.exists()
