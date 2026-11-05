from __future__ import annotations

import re
from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.steps import export as export_module
from videoflow.steps.base import StepIO
from videoflow.steps.export import ExportParams, ExportStep
from videoflow.steps.video_export import VideoExportParams, VideoExportStep


def _context(tmp_path: Path) -> PipelineContext:
    source = tmp_path / "Kimi.mp4"
    source.write_bytes(b"fixture")
    return PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        state=ProjectState(
            media_info=MediaInfo(
                source_path=str(source),
                duration_frames=30,
                fps_num=30,
                fps_den=1,
                width=640,
                height=360,
                audio_sample_rate=48000,
            )
        ),
    )


def test_export_step_uses_timestamped_basename(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seen: dict[str, str] = {}

    def fake_export(state, directory, **kwargs):
        basename = str(kwargs["basename"])
        seen["basename"] = basename
        path = Path(directory) / f"{basename}.fcpxml"
        path.write_text("<fcpxml/>", encoding="utf-8")
        return {"resolve": path}

    monkeypatch.setattr(export_module, "export_timeline", fake_export)
    context = _context(tmp_path)
    ExportStep().run(context, ExportParams(targets=["resolve"]), StepIO())
    assert re.fullmatch(r"Kimi_VideoFlow_Edited_\d{12}", seen["basename"])
    assert Path(context.artifacts["resolve"]).is_file()
    assert context.metadata["export_filename_mode"] == "source_timestamp"


def test_export_steps_are_not_cached_when_timestamped() -> None:
    assert ExportStep().is_cacheable(ExportParams()) is False
    assert ExportStep().is_cacheable(
        ExportParams(filename_mode="fixed")
    ) is True
    assert VideoExportStep().is_cacheable(VideoExportParams()) is False
    assert VideoExportStep().is_cacheable(
        VideoExportParams(filename_mode="fixed")
    ) is True
