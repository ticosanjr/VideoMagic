from __future__ import annotations

from pathlib import Path

from videoflow.application.decoupage_calibration import calibrate, read_baseline


def _xmeml(path: Path) -> Path:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<xmeml version="4">
  <sequence>
    <rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate>
    <media><video><track>
      <clipitem id="clip-1">
        <start>0</start><end>50</end><in>100</in><out>150</out>
      </clipitem>
      <clipitem id="clip-2">
        <start>50</start><end>100</end><in>300</in><out>350</out>
      </clipitem>
    </track></video></media>
  </sequence>
</xmeml>
""",
        encoding="utf-8",
    )
    return path


def _fcpxml(path: Path) -> Path:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<fcpxml version="1.9">
  <resources>
    <format id="r1" frameDuration="1/25s"/>
  </resources>
  <library><event><project><sequence>
    <spine>
      <asset-clip offset="0s" start="0s" duration="2s"/>
      <asset-clip offset="2s" start="2s" duration="2s"/>
    </spine>
  </sequence></project></event></library>
</fcpxml>
""",
        encoding="utf-8",
    )
    return path


def test_xmeml_reference_is_parsed(tmp_path: Path) -> None:
    fmt, fps, ranges = read_baseline(_xmeml(tmp_path / "reference.xml"))
    assert fmt == "xmeml"
    assert fps == 25.0
    assert len(ranges) == 2
    assert ranges[0].source_in_frame == 100
    assert ranges[0].timeline_out_frame == 50


def test_fcpxml_reference_is_parsed(tmp_path: Path) -> None:
    fmt, fps, ranges = read_baseline(_fcpxml(tmp_path / "reference.fcpxml"))
    assert fmt == "fcpxml"
    assert fps == 25.0
    assert len(ranges) == 2
    assert ranges[1].source_in_frame == 50
    assert ranges[1].source_out_frame == 100


def test_calibration_reports_overlap_and_strictness(tmp_path: Path) -> None:
    report = calibrate(
        _xmeml(tmp_path / "reference.xml"),
        source_duration_frames=1000,
        current_ranges=[(100, 150)],
    )
    assert report.baseline_cut_count == 2
    assert report.kept_ratio == 0.1
    assert report.recommended_strictness == "aggressive"
    assert report.overlap_ratio == 0.5
    assert report.to_dict()["source_ranges"][0]["source_in_frame"] == 100


def test_calibration_step_writes_a_profile(tmp_path: Path, monkeypatch) -> None:
    from videoflow.core.context import PipelineContext
    from videoflow.domain.state import MediaInfo
    from videoflow.steps.base import StepIO
    from videoflow.steps.decoupage import DecoupageCalibrateParams, DecoupageCalibrateStep

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    output = tmp_path / "out"
    (output / "decoupage").mkdir(parents=True)
    _xmeml(output / "decoupage" / "baseline.xml")
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
        media=MediaInfo(
            source_path=str(tmp_path / "source.mp4"),
            duration_frames=1000,
            fps_num=25,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        ),
    )
    DecoupageCalibrateStep().run(
        context,
        DecoupageCalibrateParams(baseline_path="decoupage/baseline.xml"),
        StepIO(),
    )
    profile = context.metadata["decoupage_profile"]
    assert profile["available"] is True
    assert profile["recommended_strictness"] == "aggressive"
    assert (output / "decoupage" / "profile.md").is_file()
