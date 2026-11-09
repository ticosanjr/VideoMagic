from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from videoflow.application import hilt
from videoflow.application.decoupage_calibration import (
    _time_frames,
    read_baseline,
    write_report,
)
from videoflow.application.style_guide import (
    color_name,
    palette_from_image,
    palette_from_images,
)
from videoflow.domain.errors import HiltAttachmentError, HiltResponseError, IngestError
from videoflow.domain.hilt import HiltFileRequest, HiltQuestion


def test_style_palette_without_ffmpeg(monkeypatch) -> None:
    monkeypatch.setattr("videoflow.application.style_guide.find_binary", lambda _: None)
    assert palette_from_image(Path("x.png")) == []
    assert palette_from_images([Path("x.png")]) == []
    assert color_name("#ff0000") == "#FF0000"
    assert color_name("bad") == "bad"


def test_style_palette_from_raw_pixels(monkeypatch, tmp_path: Path) -> None:
    pixels = np.zeros((64, 64, 3), dtype=np.uint8)
    pixels[:32, :, :] = [200, 20, 20]
    pixels[32:, :, :] = [10, 20, 200]
    monkeypatch.setattr(
        "videoflow.application.style_guide.find_binary", lambda _: "/bin/ffmpeg"
    )
    monkeypatch.setattr(
        "videoflow.application.style_guide.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=pixels.tobytes()),
    )
    colors = palette_from_image(tmp_path / "image.png", colors=2)
    assert len(colors) == 2
    assert all(item.startswith("#") for item in colors)


def test_decoupage_helpers_and_errors(tmp_path: Path) -> None:
    assert _time_frames("1001/24000s", 24) == 1
    assert _time_frames("2s", 25) == 50
    assert _time_frames("10", 25) == 10
    assert _time_frames("bad", 25) == 0
    broken = tmp_path / "broken.xml"
    broken.write_text("<not-xml")
    with pytest.raises(IngestError):
        read_baseline(broken)
    unsupported = tmp_path / "unsupported.xml"
    unsupported.write_text("<root/>")
    with pytest.raises(IngestError):
        read_baseline(unsupported)


def test_hilt_lifecycle_edges(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, token = hilt.create_request(
        output,
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        questions=[HiltQuestion(id="topic", label="Topic", required=False)],
        channels=["local", "email"],
    )
    assert hilt.make_interaction_id("a b", "c/d").startswith("hilt-")
    assert hilt.list_requests(output)[0].interaction_id == request.interaction_id
    with pytest.raises(HiltResponseError):
        hilt.respond(output, "", request.interaction_id, answers={}, channel="email")
    with pytest.raises(HiltResponseError):
        hilt.respond(output, "", request.interaction_id, action="bad")
    with pytest.raises(HiltResponseError):
        hilt.respond(output, "", request.interaction_id, answers={"unknown": "x"})
    assert hilt.is_expired(request) is False
    hilt.cancel_request(output, request.interaction_id)
    assert hilt.load_request(output, request.interaction_id).status == "cancelled"  # type: ignore[union-attr]
    assert hilt.load_response(output, request.interaction_id) is None


def test_hilt_attachment_edges(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _token = hilt.create_request(
        output,
        step_id="files",
        gate_id="files",
        kind="files",
        title="Files",
        files=[
            HiltFileRequest(
                id="a",
                label="A",
                required=False,
                accept=[".md"],
                target="research/out.md",
                allow_replace=False,
            )
        ],
    )
    with pytest.raises(HiltResponseError):
        hilt.save_attachment(
            output, request.interaction_id, request_id="missing", filename="a.md", data=b"x"
        )
    with pytest.raises(HiltAttachmentError):
        hilt.save_attachment(
            output, request.interaction_id, request_id="a", filename="a.exe", data=b"x"
        )
    attachment = hilt.save_attachment(
        output, request.interaction_id, request_id="a", filename="a.md", data=b"x"
    )
    (output / "research").mkdir(exist_ok=True)
    (output / "research" / "out.md").write_text("old", encoding="utf-8")
    response = hilt.respond(
        output, "", request.interaction_id, attachments=[attachment]
    )[1]
    with pytest.raises(HiltAttachmentError):
        hilt.apply_attachments(output, request, response)


def test_hilt_public_and_channels() -> None:
    from videoflow.domain.hilt import HiltRequest

    request = HiltRequest(interaction_id="hilt-a", title="A", job_id="j")
    payload = hilt.public_payload(Path("/tmp"), request)
    assert payload["response_url"].endswith("/respond")
    assert hilt.channels_status()["channels"][0]["id"] == "local"
    assert hilt.test_local_channel("x")["ok"] is True
    assert hilt.unresolved_files(request, hilt.HiltResponse(interaction_id="hilt-a")) == []
    assert json.loads(json.dumps(payload))["interaction_id"] == "hilt-a"


def test_write_report_roundtrip(tmp_path: Path) -> None:
    from videoflow.application.decoupage_calibration import CalibrationReport

    report = CalibrationReport(
        baseline_path="x",
        format="xmeml",
        fps=25,
        source_duration_frames=100,
        baseline_cut_count=2,
        baseline_duration_frames=50,
        kept_ratio=0.5,
        warnings=["warn"],
    )
    json_path, md_path = write_report(tmp_path / "out", report)
    assert json_path.is_file() and md_path.is_file()
    assert "warn" in md_path.read_text()
