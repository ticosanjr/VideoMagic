from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.contract.test_exporters import sample_state
from videoflow.exporters.extras import NleBroll, NleExtras, NleMarker, NleTitle
from videoflow.exporters.fcpxml import export_fcpxml
from videoflow.exporters.kdenlive import export_kdenlive
from videoflow.exporters.xmeml import export_xmeml


def extras(tmp_path: Path) -> NleExtras:
    return NleExtras(
        markers=(NleMarker(name="Hook", start_sec=1.5, note="energy peak"),),
        titles=(
            NleTitle(text="First line", start_sec=0.5, end_sec=2.5),
            NleTitle(text="Speaker", start_sec=3.0, end_sec=5.0, kind="lower_third"),
        ),
        broll=(NleBroll(path=str(tmp_path / "broll.mp4"), start_sec=2.0, duration_sec=2.0),),
        color_filters=("eq=contrast=1.1",),
        audio_filters=("loudnorm=I=-14",),
        audio_stem=str(tmp_path / "master.wav"),
    )


def test_fcpxml_exports_native_finishing(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    output = export_fcpxml(state, tmp_path / "timeline.fcpxml", extras=extras(tmp_path))
    root = ET.parse(output).getroot()

    assert len(root.findall(".//spine/title")) == 2
    assert len(root.findall(".//sequence/marker")) == 1
    assert len(root.findall(".//spine/asset-clip/filter-video")) == 2
    assert len(root.findall(".//spine/asset-clip[@lane='2']")) == 1
    assert len(root.findall(".//spine/asset-clip[@lane='4']")) == 1


def test_xmeml_exports_native_finishing(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    output = export_xmeml(state, tmp_path / "timeline.xml", extras=extras(tmp_path))
    root = ET.parse(output).getroot()

    assert len(root.findall(".//video/track/generatoritem")) == 2
    assert len(root.findall(".//sequence/marker")) == 1
    assert len(
        root.findall(".//video/track/clipitem/filter/effect[name='Color Correction']")
    ) == 2
    assert len(root.findall(".//video/track")) == 2
    assert len(root.findall(".//audio/track")) == 2


def test_kdenlive_exports_native_finishing(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    output = export_kdenlive(state, tmp_path / "timeline.kdenlive", extras=extras(tmp_path))
    root = ET.parse(output).getroot()

    titles = root.findall("./producer/property[.='kdenlivetitle']")
    assert len(titles) == 2
    guides = root.find(
        "./playlist[@id='main_bin']/property[@name='kdenlive:docproperties.guides']"
    )
    assert guides is not None and "Hook" in (guides.text or "")
    assert root.find("./playlist[@id='playlist4']") is not None
    assert root.find("./playlist[@id='playlist5']") is not None
    services = {
        item.text for item in root.findall(".//property[@name='mlt_service']")
    }
    assert "lift_gamma_gain" in services
    assert "qtblend" in services


def test_qa_script_accepts_a_finished_export(tmp_path: Path) -> None:
    from scripts.qa_nle import main

    state = sample_state(tmp_path)
    output = tmp_path / "exports"
    output.mkdir()
    job = tmp_path / "job"
    (job / "color").mkdir(parents=True)
    (job / "audio").mkdir()
    (job / "titles.ass").write_text(
        "[Events]\nDialogue: 0,0:00:00.50,0:00:02.50,Default,,0,0,0,,First line\n",
        encoding="utf-8",
    )
    (job / "timeline_meta.json").write_text(
        json.dumps(
            {
                "markers": [
                    {"id": "m1", "time_sec": 1.0, "label": "Hook", "color": "#fff"}
                ],
                "tracks": {},
            }
        ),
        encoding="utf-8",
    )
    (job / "color" / "filters.json").write_text(
        '{"filters": ["eq=contrast=1.1"]}', encoding="utf-8"
    )
    (job / "audio" / "master.wav").write_bytes(b"RIFF")
    overlay = tmp_path / "logo.png"
    overlay.write_bytes(b"png")
    (job / "project_state.json").write_text(
        json.dumps(
            {
                "media_info": {"fps_num": 30, "fps_den": 1},
                "overlays": [
                    {
                        "overlay_id": "o1",
                        "path": str(overlay),
                        "start_frame": 30,
                        "duration_frames": 60,
                        "kind": "image",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (job / "chapters.json").write_text(
        json.dumps({"chapters": [{"title": "Intro", "start_sec": 2.0}]}),
        encoding="utf-8",
    )
    broll = tmp_path / "broll.mp4"
    broll.write_bytes(b"x")
    (job / "broll.json").write_text(
        json.dumps(
            {
                "Short one": [
                    {"path": str(broll), "start_sec": 1.0, "duration_sec": 2.0}
                ]
            }
        ),
        encoding="utf-8",
    )
    from videoflow.application.nle_extras import nle_extras_from_output

    used = nle_extras_from_output(job)
    export_fcpxml(state, output / "timeline.fcpxml", extras=used)
    export_xmeml(state, output / "timeline.xml", extras=used)
    export_kdenlive(state, output / "timeline.kdenlive", extras=used)

    report = main([str(output), "--job-output", str(job), "--json"])
    assert report == 0
    import xml.etree.ElementTree as ET

    root = ET.parse(output / "timeline.fcpxml").getroot()
    assert len(root.findall(".//sequence/marker")) == 2
    kdenlive = ET.parse(output / "timeline.kdenlive").getroot()
    assert kdenlive.findall("./producer/property[.='qimage']")
    xmeml = ET.parse(output / "timeline.xml").getroot()
    assert xmeml.findall(".//video/track/clipitem/stillframe")
