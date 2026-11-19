from __future__ import annotations

from pathlib import Path

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.application.projects import init_project, save_project_state
from videoflow.application.shorts_batch import run_shorts_batch
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)

RATE = 48_000


def _project(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    record, _ = init_project(name="Batch", output=tmp_path / "out")
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
        start_sample=0,
        end_sample=5 * RATE,
        text="Uma frase completa.",
        words=[WordTiming(word="Uma", start_sample=0, end_sample=RATE, probability=0.9)],
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
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="a1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=5 * RATE,
                timeline_in_sample=0,
                timeline_out_sample=5 * RATE,
            )
        ],
    )
    state.pipeline.speech_intervals = [(0, 5 * RATE)]
    save_project_state(record, state, bump_revision=False)
    return record


def test_batch_passes_aspect_and_dedicated_layouts(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    calls: list[dict[str, object]] = []

    def fake_render(self, source, pieces, destination, **kwargs):
        calls.append(kwargs)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"mp4")
        return Path(destination)

    monkeypatch.setattr(FFmpegAdapter, "render_short", fake_render)
    layouts = [
        "split_top_visual",
        "headline_card",
        "fullscreen_punchin",
        "pip_bottom_right",
    ]
    result = run_shorts_batch(
        record.project_id,
        [
            {
                "title": layout,
                "start_sec": 0,
                "end_sec": 5,
                "aspect_ratio": "4:5",
                "layout_mode": layout,
                "headline_text": "Manchete" if layout == "headline_card" else "",
                "overlay_path": str(tmp_path / "overlay.png")
                if layout == "pip_bottom_right"
                else "",
                "visual_path": str(tmp_path / "visual.png")
                if layout == "split_top_visual"
                else "",
            }
            for layout in layouts
        ],
    )

    assert result["ok"] is True
    assert [item["layout"] for item in result["clips"]] == layouts
    assert all(call["width"] == 1080 and call["height"] == 1350 for call in calls)
    assert calls[0]["layout_mode"] == "split_top_visual"
    assert calls[1]["layout_mode"] == "headline_card"
    assert calls[1]["headline_text"] == "Manchete"
    assert calls[2]["layout_mode"] == "fullscreen_punchin"
    assert calls[3]["layout_mode"] == "pip_bottom_right"
    assert calls[3]["overlay_path"] == tmp_path / "overlay.png"


def test_batch_rejects_unknown_layout(tmp_path: Path, monkeypatch) -> None:
    record = _project(tmp_path, monkeypatch)
    with __import__("pytest").raises(Exception, match="Unsupported Short layout"):
        run_shorts_batch(
            record.project_id,
            [{"title": "bad", "start_sec": 0, "end_sec": 2, "layout_mode": "nope"}],
        )
