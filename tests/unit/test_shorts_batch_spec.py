from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from videoflow.application.projects import init_project, save_project_state
from videoflow.application.shorts_batch import run_shorts_batch
from videoflow.domain.errors import ExportError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)

RATE = 48_000


def _project(tmp_path: Path, monkeypatch) -> object:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    record, _ = init_project(name="Spec batch", output=tmp_path / "out")
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
        end_sample=7 * RATE,
        text="Trecho mapeado.",
        words=[
            WordTiming(
                word="Trecho",
                start_sample=5 * RATE,
                end_sample=7 * RATE,
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
                source_in_frame=240,
                source_out_frame=300,
                timeline_in_frame=150,
                timeline_out_frame=210,
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
                source_in_sample=8 * RATE,
                source_out_sample=10 * RATE,
                timeline_in_sample=5 * RATE,
                timeline_out_sample=7 * RATE,
            ),
        ],
    )
    state.pipeline.speech_intervals = [(5 * RATE, 7 * RATE)]
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


def test_batch_rejects_unknown_clip_key(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    with pytest.raises(ValidationError):
        run_shorts_batch(
            record.project_id,
            [{"start_sec": 0, "end_sec": 1, "margin_top": 20}],
            adapter=_Renderer(),
        )


def test_batch_maps_source_time_to_timeline(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    renderer = _Renderer()
    result = run_shorts_batch(
        record.project_id,
        [
            {
                "start_sec": 8,
                "end_sec": 10,
                "time_basis": "source",
                "source_id": "primary",
                "title": "Mapped",
            }
        ],
        adapter=renderer,
    )
    clip = result["clips"][0]
    assert clip["start_sec"] == pytest.approx(5.0, abs=0.1)
    assert clip["end_sec"] == pytest.approx(7.0, abs=0.1)


def test_batch_passes_fps_to_renderer(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    renderer = _Renderer()
    run_shorts_batch(
        record.project_id,
        [{"start_sec": 5, "end_sec": 7, "title": "Sixty", "fps": 60}],
        adapter=renderer,
    )
    assert renderer.calls[0]["fps"] == 30


def test_batch_rejects_missing_intro_asset(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    with pytest.raises(ExportError, match="asset_not_found"):
        run_shorts_batch(
            record.project_id,
            [
                {
                    "start_sec": 5,
                    "end_sec": 7,
                    "title": "Intro",
                    "intro_path": str(tmp_path / "missing.png"),
                }
            ],
            adapter=_Renderer(),
        )


def test_batch_rejects_clip_below_min_sec(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    with pytest.raises(ExportError, match="below min_sec"):
        run_shorts_batch(
            record.project_id,
            [
                {
                    "start_sec": 5,
                    "end_sec": 7,
                    "title": "Too short",
                    "min_sec": 10.0,
                }
            ],
            adapter=_Renderer(),
        )
