"""Structural validation of FCPXML, XMEML, and Kdenlive exports."""

from __future__ import annotations

from pathlib import Path

from videoflow.application.nle_validation import main, validate_nle_exports


def write(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


FCPXML = """<?xml version="1.0"?>
<fcpxml version="1.9">
  <resources>
    <asset id="r1"><media-rep src="file:///clip.mp4"/></asset>
  </resources>
  <library><event><project><sequence>
    <spine>
      <asset-clip ref="r1" lane="1"><filter-video><effect/></filter-video></asset-clip>
      <transition><effect/></transition>
      <asset-clip ref="r1" lane="2"/>
      <asset-clip ref="r1" lane="4"/>
      <title>Title</title>
    </spine>
    <marker/>
  </sequence></project></event></library>
</fcpxml>
"""

XMEML = """<?xml version="1.0"?>
<xmeml version="5">
  <sequence>
    <media>
      <video>
        <track>
          <clipitem><filter><effect><name>Color</name></effect></filter></clipitem>
          <transitionitem/>
        </track>
      </video>
      <audio><track><clipitem/></track></audio>
    </media>
    <marker/>
  </sequence>
</xmeml>
"""

KDENLIVE = """<?xml version="1.0"?>
<mlt>
  <profile/>
  <producer><property>kdenlivetitle</property></producer>
  <chain/>
  <playlist id="playlist_v1"><entry><filter>
    <property name="mlt_service">lift_gamma_gain</property>
  </filter></entry></playlist>
  <playlist id="playlist_v2"><entry/></playlist>
  <playlist id="main_bin"><property name="kdenlive:docproperties.guides">x</property></playlist>
  <playlist id="playlist4"/>
  <playlist id="playlist5"/>
  <tractor><transition><property name="mlt_service">qtblend</property></transition></tractor>
</mlt>
"""


def test_timestamped_exports_validate(tmp_path: Path) -> None:
    base = "Kimi_VideoFlow_Edited_261105143012"
    write(tmp_path, f"{base}.fcpxml", FCPXML)
    write(tmp_path, f"{base}.xml", XMEML)
    write(tmp_path, f"{base}.kdenlive", KDENLIVE)

    report = validate_nle_exports(tmp_path)

    assert report["ok"] is True
    assert report["exports"]["fcpxml"]["path"].endswith(f"{base}.fcpxml")
    assert report["exports"]["xmeml"]["path"].endswith(f"{base}.xml")
    assert report["exports"]["kdenlive"]["path"].endswith(f"{base}.kdenlive")


def test_all_exports_validate(tmp_path: Path) -> None:
    write(tmp_path, "timeline.fcpxml", FCPXML)
    write(tmp_path, "timeline.xml", XMEML)
    write(tmp_path, "timeline.kdenlive", KDENLIVE)

    report = validate_nle_exports(tmp_path)

    assert report["ok"] is True
    assert report["directory"] == str(tmp_path)
    fcpxml = report["exports"]["fcpxml"]
    assert fcpxml["clips"] == 3
    assert fcpxml["broll_clips"] == 1
    assert fcpxml["audio_stems"] == 1
    assert fcpxml["color_filters"] == 1
    assert fcpxml["titles"] == 1
    assert report["exports"]["xmeml"]["clips"] == 1
    assert report["exports"]["xmeml"]["effects"] == 1
    assert report["exports"]["xmeml"]["video_tracks"] == 1
    kdenlive = report["exports"]["kdenlive"]
    assert kdenlive["clips"] == 2
    assert kdenlive["color_filters"] == 1
    assert kdenlive["overlay_track"] == 1
    assert kdenlive["audio_stem"] == 1
    assert kdenlive["guides"] == 1


def test_missing_files_fail_without_raising(tmp_path: Path) -> None:
    report = validate_nle_exports(tmp_path)

    assert report["ok"] is False
    for check in report["exports"].values():
        assert check["ok"] is False
        assert check["errors"] == ["missing file"]


def test_parse_errors_are_reported(tmp_path: Path) -> None:
    write(tmp_path, "timeline.fcpxml", "<fcpxml>")
    write(tmp_path, "timeline.xml", "<xmeml>")
    write(tmp_path, "timeline.kdenlive", "<mlt>")

    report = validate_nle_exports(tmp_path)

    for check in report["exports"].values():
        assert check["ok"] is False
        assert any("parse error" in error for error in check["errors"])


def test_wrong_roots_and_empty_timelines_fail(tmp_path: Path) -> None:
    write(tmp_path, "timeline.fcpxml", "<notfcpxml/>")
    write(tmp_path, "timeline.xml", "<notxmeml/>")
    write(tmp_path, "timeline.kdenlive", "<notmlt/>")

    report = validate_nle_exports(tmp_path)

    assert report["ok"] is False
    assert "root is not fcpxml" in report["exports"]["fcpxml"]["errors"]
    assert "root is not xmeml" in report["exports"]["xmeml"]["errors"]
    assert "root is not mlt" in report["exports"]["kdenlive"]["errors"]
    assert "no asset-clip in sequence spine" in report["exports"]["fcpxml"]["errors"]
    assert "no video clipitem" in report["exports"]["xmeml"]["errors"]
    assert "no audio clipitem" in report["exports"]["xmeml"]["errors"]
    assert "no media chain" in report["exports"]["kdenlive"]["errors"]


def test_missing_transitions_are_warnings_not_errors(tmp_path: Path) -> None:
    write(
        tmp_path,
        "timeline.fcpxml",
        """<fcpxml><resources><asset><media-rep/></asset></resources>
        <library><event><project><sequence><spine>
        <asset-clip/><asset-clip/>
        </spine></sequence></project></event></library></fcpxml>""",
    )

    report = validate_nle_exports(tmp_path)

    check = report["exports"]["fcpxml"]
    assert check["ok"] is True
    assert "no transition elements" in check["warnings"]
    assert "some joins have no transition" in check["warnings"]


def test_kdenlive_missing_profile_is_an_error(tmp_path: Path) -> None:
    write(
        tmp_path,
        "timeline.kdenlive",
        "<mlt><chain/><playlist id='playlist_v1'><entry/></playlist></mlt>",
    )

    report = validate_nle_exports(tmp_path)

    check = report["exports"]["kdenlive"]
    assert check["ok"] is False
    assert "missing profile" in check["errors"]


def test_main_requires_one_argument(tmp_path: Path, capsys) -> None:
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_main_prints_json_and_returns_status(tmp_path: Path, capsys) -> None:
    assert main([str(tmp_path)]) == 1
    assert '"ok": false' in capsys.readouterr().out

    write(tmp_path, "timeline.fcpxml", FCPXML)
    write(tmp_path, "timeline.xml", XMEML)
    write(tmp_path, "timeline.kdenlive", KDENLIVE)

    assert main([str(tmp_path)]) == 0
    assert '"ok": true' in capsys.readouterr().out
