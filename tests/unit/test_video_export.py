from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.steps import video_export
from videoflow.steps.base import StepIO
from videoflow.steps.export import ExportParams
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
    artifact = Path(context.artifacts["video"])
    assert artifact.name.startswith("source_VideoFlow_Edited_")
    assert artifact.suffix == ".mp4"
    assert artifact.is_file()
    assert context.metadata["video_filename_mode"] == "source_timestamp"


def test_video_export_fixed_filename_mode(tmp_path: Path, monkeypatch) -> None:
    def fake_export(state, destination, **kwargs):
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
    VideoExportStep().run(
        context,
        VideoExportParams(filename_mode="fixed", filename="custom.mp4"),
        StepIO(),
    )
    assert context.artifacts["video"].endswith("custom.mp4")
    assert (tmp_path / "out" / "exports" / "custom.mp4").is_file()


def test_legacy_nle_mp4_target_is_removed() -> None:
    params = ExportParams(targets=["mp4", "resolve"])
    assert params.targets == ["resolve"]
