"""v4.8.0 Shorts face centering, ASS header, and vf_shorts schema."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from videoflow.application import face_track
from videoflow.application.captions import CaptionLine, build_ass_lines
from videoflow.application.projects import init_project, save_project_state
from videoflow.application.short_composition.captions import (
    CaptionBlock,
    build_short_ass,
)
from videoflow.application.shorts_batch import run_shorts_batch
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)
from videoflow.mcp_server.core_tools.official import register_official_tools

RATE = 48_000


class _FakeCascade:
    def __init__(self, _path: str) -> None:
        pass

    def empty(self) -> bool:
        return False

    def detectMultiScale(self, image, **_kwargs):
        height, width = image.shape[:2]
        if width < 1500:
            return ()
        face_w = max(40, int(width * 0.09))
        face_h = max(60, int(height * 0.18))
        center_x = int(width * 0.72)
        center_y = int(height * 0.35)
        return np.array(
            [[center_x - face_w // 2, center_y - face_h // 2, face_w, face_h]],
            dtype=np.int32,
        )


def _frames() -> list[np.ndarray]:
    return [np.zeros((1080, 1920, 3), dtype=np.uint8) for _ in range(7)]


def test_detect_face_median_x_reads_a_face_at_72_percent(monkeypatch) -> None:
    monkeypatch.setattr(face_track, "_sample_video_frames", lambda *a, **k: _frames())
    monkeypatch.setattr(face_track, "_haar_detector", lambda: _FakeCascade(""))

    result = face_track.detect_face_median_x("synthetic.mp4", 0.0, 2.0)

    assert result["backend"] == "opencv-haar"
    assert result["detections"] == 7
    assert result["samples"] == 7
    assert result["face_fallback_center"] is False
    assert result["cx_median"] == pytest.approx(0.72, abs=0.01)
    assert result["cy_median"] == pytest.approx(0.35, abs=0.01)


def test_detect_face_median_x_reports_the_center_fallback(monkeypatch) -> None:
    class _EmptyCascade(_FakeCascade):
        def detectMultiScale(self, image, **_kwargs):
            return ()

    monkeypatch.setattr(face_track, "_sample_video_frames", lambda *a, **k: _frames())
    monkeypatch.setattr(face_track, "_haar_detector", lambda: _EmptyCascade(""))

    result = face_track.detect_face_median_x("synthetic.mp4", 0.0, 2.0)

    assert result["cx_median"] is None
    assert result["detections"] == 0
    assert result["backend"] == "none"
    assert result["face_fallback_center"] is True


def _project(tmp_path: Path, monkeypatch) -> object:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    record, _ = init_project(name="Face batch", output=tmp_path / "out")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=300,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=RATE,
    )
    sentence = Sentence(
        id=0,
        start_sample=5 * RATE,
        end_sample=10 * RATE,
        text="Trecho mapeado para o Short.",
        words=[
            WordTiming(
                word="Trecho",
                start_sample=5 * RATE,
                end_sample=10 * RATE,
                probability=0.9,
            )
        ],
    )
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        transcript=[sentence],
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=150,
                timeline_in_frame=0,
                timeline_out_frame=150,
            ),
            VideoSegment(
                clip_id="v2",
                source_id="primary",
                source_in_frame=210,
                source_out_frame=300,
                timeline_in_frame=150,
                timeline_out_frame=240,
            ),
        ],
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=5 * RATE,
                timeline_in_sample=0,
                timeline_out_sample=5 * RATE,
            ),
            AudioSegment(
                clip_id="a2",
                source_id="primary",
                source_in_sample=7 * RATE,
                source_out_sample=10 * RATE,
                timeline_in_sample=5 * RATE,
                timeline_out_sample=8 * RATE,
            ),
        ],
    )
    state.pipeline.speech_intervals = [(5 * RATE, 10 * RATE)]
    save_project_state(record, state, bump_revision=False)
    return record


class _Renderer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def render_short(self, source, pieces, destination, **kwargs):
        self.calls.append(kwargs)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"short")
        return Path(destination)


def test_batch_injects_the_face_crop_and_records_it(
    tmp_path: Path, monkeypatch
) -> None:
    record = _project(tmp_path, monkeypatch)
    renderer = _Renderer()
    monkeypatch.setattr(
        "videoflow.application.shorts_batch.detect_face_median_x",
        lambda *a, **k: {
            "cx_median": 0.72,
            "cy_median": 0.35,
            "detections": 7,
            "samples": 7,
            "backend": "opencv-haar",
            "face_fallback_center": False,
        },
    )

    result = run_shorts_batch(
        record.project_id,
        [{"start_sec": 5, "end_sec": 10, "title": "Face"}],
        adapter=renderer,
    )

    clip = result["clips"][0]
    assert clip["crop_w"] == 608
    assert clip["crop_h"] == 1080
    assert clip["crop_x"] == 1078
    assert clip["crop_x"] != 656
    assert clip["face_cx_median"] == pytest.approx(0.72)
    assert clip["face_backend"] == "opencv-haar"
    assert clip["face_fallback_center"] is False
    assert renderer.calls[0]["source_crop"] == (608, 1080, 1078, 0)
    assert renderer.calls[0]["crop_focus_x"] == pytest.approx(0.821646, abs=1e-4)

    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["clips"][0]["crop_x"] == 1078
    assert manifest["clips"][0]["face_backend"] == "opencv-haar"


def test_short_ass_header_is_wrap0_margin140_and_centered() -> None:
    ass = build_short_ass(
        [CaptionBlock(start=0.0, end=1.0, lines=("HELLO",), subtitle_y=1340)]
    )
    assert "WrapStyle: 0" in ass
    assert "5,140,140,0,1" in ass
    assert "\\an5\\pos(540,1340)" in ass

    shared = build_ass_lines(
        [CaptionLine(start=0.0, end=1.0, text="HELLO")],
        width=1080,
        height=1920,
    )
    assert "WrapStyle: 0" in shared
    assert "140,140" in shared
    assert "\\pos(540,1340)" in shared
    assert "\\pos(500," not in shared


def test_vf_shorts_signature_and_batch_delegation() -> None:
    registered: dict[str, object] = {}
    calls: dict[str, object] = {}

    def register(function):
        registered[function.__name__] = function
        return function

    def batch(project_id, clips, wait=True):
        calls["batch"] = {"project_id": project_id, "clips": clips, "wait": wait}
        return {"ok": True, "clips": clips}

    def run(**kwargs):
        calls.setdefault("run", []).append(kwargs)
        return {"ok": True, "steps": kwargs.get("steps")}

    register_official_tools(
        register,
        {
            "vf_shorts_batch": batch,
            "vf_run": run,
            "vf_qa_final": lambda **_kwargs: {"ok": True},
            "vf_job": lambda **_kwargs: {"ok": True},
        },
    )
    tool = registered["vf_shorts"]
    signature = inspect.signature(tool)
    assert list(signature.parameters) == [
        "project_id",
        "action",
        "clips",
        "time_basis",
        "burn_subtitles",
        "wait",
    ]
    default = signature.parameters["action"].default
    assert default == "batch"

    result = tool(
        project_id="p1",
        clips=[{"start_sec": 1, "end_sec": 4}],
        time_basis="source",
        burn_subtitles=False,
    )
    assert result["ok"] is True
    sent = calls["batch"]
    assert sent["clips"] == [
        {
            "start_sec": 1,
            "end_sec": 4,
            "time_basis": "source",
            "burn_subtitles": False,
        }
    ]

    tool(project_id="p1", action="select")
    assert calls["run"][0]["steps"] == ["shorts.select"]
