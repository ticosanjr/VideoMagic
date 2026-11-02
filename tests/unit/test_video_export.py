from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.steps import video_export
from videoflow.steps.base import StepIO
from videoflow.steps.video_export import VideoExportParams, VideoExportStep


def test_video_export_uses_ultrafast_by_default(tmp_path: Path, monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_export(state, destination, **kwargs):
        seen.update(kwargs)
        Path(destination).write_bytes(b"video")
        return Path(destination)

    monkeypatch.setattr(video_export, "export_mp4", fake_export)
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        state=ProjectState(
            media_info=MediaInfo(
                source_path=str(tmp_path / "source.mp4"),
                duration_frames=30,
                fps_num=30,
                fps_den=1,
                width=640,
                height=360,
                audio_sample_rate=48000,
            )
        ),
    )
    VideoExportStep().run(context, VideoExportParams(), StepIO())
    assert seen["preset"] == "ultrafast"
    assert seen["crf"] == 30
    assert context.artifacts["video"].endswith("video.mp4")
    assert (tmp_path / "out" / "exports" / "video.mp4").is_file()
