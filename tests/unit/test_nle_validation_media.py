"""Cross-validation of NLE media references and durations."""

from __future__ import annotations

from pathlib import Path

from videoflow.application.nle_validation import validate_nle_exports
from videoflow.domain.state import AudioSegment, MediaInfo, ProjectState, VideoSegment
from videoflow.exporters.fcpxml import export_fcpxml
from videoflow.exporters.kdenlive import export_kdenlive
from videoflow.exporters.xmeml import export_xmeml


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


def _exports(tmp_path: Path, state: ProjectState) -> Path:
    directory = tmp_path / "exports"
    directory.mkdir()
    export_fcpxml(state, directory / "timeline.fcpxml")
    export_xmeml(state, directory / "timeline.xml")
    export_kdenlive(state, directory / "timeline.kdenlive")
    return directory


def test_valid_exports_pass_media_and_duration_checks(tmp_path: Path) -> None:
    state = _state(tmp_path)
    directory = _exports(tmp_path, state)

    report = validate_nle_exports(directory, timeline_frames=60, check_media=True)

    assert report["ok"] is True
    for check in report["exports"].values():
        assert check["media"]["missing"] == []
        assert check["duration"]["actual_frames"] == 60


def test_missing_reference_fails_each_export(tmp_path: Path) -> None:
    state = _state(tmp_path)
    directory = _exports(tmp_path, state)
    Path(state.media_info.source_path).unlink()

    report = validate_nle_exports(directory, timeline_frames=60, check_media=True)

    assert report["ok"] is False
    for check in report["exports"].values():
        assert check["media"]["missing"]
        assert any("missing media" in error for error in check["errors"])


def test_blocked_reference_fails(tmp_path: Path) -> None:
    state = _state(tmp_path)
    directory = _exports(tmp_path, state)

    report = validate_nle_exports(
        directory,
        blocked_paths={state.media_info.source_path},
        check_media=True,
    )

    assert report["ok"] is False
    for check in report["exports"].values():
        assert check["media"]["blocked"]


def test_duration_mismatch_fails(tmp_path: Path) -> None:
    state = _state(tmp_path)
    directory = _exports(tmp_path, state)

    report = validate_nle_exports(directory, timeline_frames=90)

    assert report["ok"] is False
    for check in report["exports"].values():
        assert check["duration"]["ok"] is False
        assert any("duration mismatch" in error for error in check["errors"])


def test_structural_validation_stays_optional(tmp_path: Path) -> None:
    state = _state(tmp_path)
    directory = _exports(tmp_path, state)
    Path(state.media_info.source_path).unlink()

    report = validate_nle_exports(directory)

    assert report["ok"] is True
    assert "media" not in report["exports"]["fcpxml"]
