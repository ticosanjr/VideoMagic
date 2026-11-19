from __future__ import annotations

from pathlib import Path

from videoflow.application.output_layout import collect_outputs
from videoflow.core.context import PipelineContext
from videoflow.steps.base import StepIO
from videoflow.steps.delivery_collect import CollectParams, DeliveryCollectStep


def test_collect_copies_videos_and_exports_to_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VF_OUTPUT_DIR", str(tmp_path / "VideoFlow_Output"))
    source = tmp_path / "project"
    (source / "exports").mkdir(parents=True)
    (source / "shorts").mkdir()
    (source / "exports" / "master.mp4").write_bytes(b"mp4")
    (source / "exports" / "timeline.fcpxml").write_text("<fcpxml/>", encoding="utf-8")
    (source / "shorts" / "clip.mp4").write_bytes(b"short")
    (source / "top.mp4").write_bytes(b"top")

    result = collect_outputs(source, project_id="demo")
    root = tmp_path / "VideoFlow_Output"
    assert result["count"] == 4
    assert (root / "exports" / "demo" / "master.mp4").is_file()
    assert (root / "exports" / "demo" / "timeline.fcpxml").is_file()
    assert (root / "shorts" / "demo" / "clip.mp4").is_file()
    assert (root / "videos" / "demo" / "top.mp4").is_file()
    assert Path(result["manifest_path"]).is_file()

    again = collect_outputs(source, project_id="demo")
    assert again["count"] == 0
    assert len(again["skipped"]) == 4


def test_delivery_collect_step_records_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VF_OUTPUT_DIR", str(tmp_path / "delivery"))
    source = tmp_path / "project"
    (source / "exports").mkdir(parents=True)
    (source / "exports" / "master.mp4").write_bytes(b"mp4")
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=source,
        work=source / "work",
        exports=source / "exports",
    )
    DeliveryCollectStep().run(context, CollectParams(mode="copy", project_id="demo"), StepIO())
    assert context.metadata["delivery_collect"]["count"] == 1
    assert Path(context.artifacts["delivery_collect"]).is_file()


def test_collect_can_move_generated_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VF_OUTPUT_DIR", str(tmp_path / "delivery"))
    source = tmp_path / "project"
    (source / "exports").mkdir(parents=True)
    artifact = source / "exports" / "master.mp4"
    artifact.write_bytes(b"mp4")
    result = collect_outputs(source, project_id="demo", mode="move")
    assert result["moved"]
    assert not artifact.exists()
    assert (tmp_path / "delivery" / "exports" / "demo" / "master.mp4").is_file()
