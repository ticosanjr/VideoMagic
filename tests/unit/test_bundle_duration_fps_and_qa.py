"""Export duration/FPS invariants, render profile precedence, and NLE lookup."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from videoflow.application import qa_final
from videoflow.application.master_export import resolve_render_profile
from videoflow.application.nle_validation import _resolve_export_path
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    VideoSegment,
)
from videoflow.exporters import mp4


def _state(tmp_path: Path, *, fps: int = 60, frames: int = 600) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=frames,
        fps_num=fps,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    video = []
    audio = []
    for index in range(2):
        start = index * (frames // 2)
        end = start + frames // 2
        video.append(
            VideoSegment(
                clip_id=f"v{index}",
                source_in_frame=start,
                source_out_frame=end,
                timeline_in_frame=start,
                timeline_out_frame=end,
            )
        )
        audio.append(
            AudioSegment(
                clip_id=f"v{index}",
                source_in_sample=start * 800,
                source_out_sample=end * 800,
                timeline_in_sample=start * 800,
                timeline_out_sample=end * 800,
            )
        )
    return ProjectState(media_info=media, video_segments=video, audio_segments=audio)


class RecordingAdapter:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def render(self, command: list[str], **kwargs: object) -> None:
        self.commands.append(list(command))
        Path(command[-1]).write_bytes(b"mp4")


def test_output_frames_preserve_ten_seconds_at_half_fps(tmp_path: Path) -> None:
    state = _state(tmp_path, fps=60, frames=600)
    assert mp4.output_render_frames(state, 30) == 300
    assert mp4.output_render_frames(state, 60) == 600


def test_segmented_group_encodes_at_the_target_fps(tmp_path: Path) -> None:
    state = _state(tmp_path, fps=60, frames=600)
    adapter = RecordingAdapter()
    target = mp4._render_video_group(
        state,
        state.media_info,
        [0, 1],
        renderer=adapter,
        source=Path(state.media_info.source_path),
        cache_dir=tmp_path / "segments",
        crf=18,
        preset="medium",
        fps=30,
        encoder="libx264",
    )
    assert target.is_file()
    command = adapter.commands[0]
    graph = command[command.index("-filter_complex") + 1]
    assert "fps=30" in graph
    assert command[command.index("-r") + 1] == "30/1"


def test_render_profile_keeps_explicit_final_and_draft_scale(tmp_path: Path) -> None:
    state = _state(tmp_path, fps=60, frames=600)
    final = resolve_render_profile(
        state, mode="final", fps=60, draft=False, draft_scale=0.5
    )
    assert final["fps"] == 60
    assert final["scale_height"] is None
    draft = resolve_render_profile(
        state, mode="final", fps=30, draft=True, draft_scale=0.5
    )
    assert draft["fps"] == 30
    assert draft["scale_height"] == 540
    preview = resolve_render_profile(state, mode="preview", fps=60)
    assert preview["fps"] == 30
    assert preview["scale_max"] == 540
    assert preview["qa_mode"] == "off"


def test_nle_lookup_finds_canonical_name_in_project_root(tmp_path: Path) -> None:
    exports = tmp_path / "project" / "exports"
    exports.mkdir(parents=True)
    canonical = tmp_path / "project" / "resolve_timeline.fcpxml"
    canonical.write_text("<fcpxml />", encoding="utf-8")
    found = _resolve_export_path(
        exports,
        ".fcpxml",
        ("resolve_timeline.fcpxml", "timeline.fcpxml"),
    )
    assert found == canonical


def test_needs_review_writes_a_review_file(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    state = _state(tmp_path)
    video = tmp_path / "final.mp4"
    video.write_bytes(b"video")
    output = tmp_path / "project"
    output.mkdir()

    monkeypatch.setattr(
        qa_final,
        "validate_integrity",
        lambda *args, **kwargs: SimpleNamespace(ok=True, to_dict=lambda: {"ok": True}),
    )
    monkeypatch.setattr(
        qa_final,
        "detect_audio_silence",
        lambda _video: [
            {
                "kind": "audio_silence",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "duration_sec": 1.0,
            }
        ],
    )
    monkeypatch.setattr(
        "videoflow.core.media_contract.validate_media",
        lambda *args, **kwargs: SimpleNamespace(ok=True, to_dict=lambda: {"ok": True}),
    )
    from videoflow.adapters.ffmpeg import FFmpegAdapter

    monkeypatch.setattr(
        FFmpegAdapter,
        "measure_loudness",
        lambda self, path: {"integrated_lufs": -16.0, "true_peak_dbfs": -2.0},
    )
    report = qa_final.audit_final(
        video,
        output=output,
        state=state,
        strict=True,
        mode="fast",
        expected_sec=10.0,
        expected_frames=600,
        fps=60,
        width=0,
        height=0,
    )
    assert report["status"] == "needs_review"
    review = json.loads((output / "review.json").read_text(encoding="utf-8"))
    assert review["approved"] is False
    assert review["pending"]
