"""Final vs. ultra-fast preview render contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application import master_export
from videoflow.application.delivery_bundle import (
    DeliveryBundleRequest,
    build_delivery_bundle,
)
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    VideoSegment,
)
from videoflow.exporters import mp4
from videoflow.exporters.mp4 import export_mp4
from videoflow.steps import video_export
from videoflow.steps.base import StepIO
from videoflow.steps.video_export import VideoExportParams, VideoExportStep


def _state(tmp_path: Path, *, width: int = 1920, height: int = 1080) -> ProjectState:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    return ProjectState(
        media_info=MediaInfo(
            source_path=str(source),
            duration_frames=30,
            fps_num=30,
            fps_den=1,
            width=width,
            height=height,
            audio_sample_rate=48000,
        ),
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
    )


class RecordingAdapter:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def render(self, command: list[str], **kwargs: object) -> None:
        self.commands.append(list(command))
        Path(command[-1]).write_bytes(b"mp4")


def test_preview_master_uses_540p_fast_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_export(*_args, **kwargs):
        captured.update(kwargs)
        return tmp_path / "preview_fast.mp4"

    monkeypatch.setattr(master_export, "export_mp4", fake_export)
    monkeypatch.setattr(master_export, "video_encoder", lambda: "libx264")
    master_export.render_master(
        _state(tmp_path),
        tmp_path / "preview_fast.mp4",
        output=tmp_path,
        mode="preview",
    )
    assert captured["mode"] == "preview"
    assert captured["scale_max"] == 540
    assert captured["scale_height"] is None
    assert captured["audio_bitrate"] == "128k"
    assert captured["loudness_lufs"] is None
    assert captured["qa_mode"] == "off"
    assert captured["fps"] == 30
    assert captured["cfr"] is True


def test_preview_encoder_flags_use_p1_or_ultrafast() -> None:
    nvenc = mp4._video_encode_args(
        crf=18,
        preset="medium",
        profile="",
        fps_num=30,
        fps_den=1,
        cfr=False,
        mode="preview",
        encoder="h264_nvenc",
    )
    assert nvenc[:2] == ["-c:v", "h264_nvenc"]
    assert nvenc[nvenc.index("-preset") + 1] == "p1"
    assert nvenc[nvenc.index("-cq") + 1] == "28"

    cpu = mp4._video_encode_args(
        crf=18,
        preset="medium",
        profile="",
        fps_num=30,
        fps_den=1,
        cfr=False,
        mode="preview",
        encoder="libx264",
    )
    assert cpu[cpu.index("-preset") + 1] == "ultrafast"
    assert cpu[cpu.index("-crf") + 1] == "30"


def test_preview_landscape_and_portrait_scaling(tmp_path: Path) -> None:
    landscape = RecordingAdapter()
    export_mp4(
        _state(tmp_path, width=1920, height=1080),
        tmp_path / "landscape.mp4",
        adapter=landscape,
        mode="preview",
        encoder="libx264",
        scale_max=540,
    )
    graph = landscape.commands[0][
        landscape.commands[0].index("-filter_complex") + 1
    ]
    assert "scale=-2:540" in graph

    portrait = RecordingAdapter()
    export_mp4(
        _state(tmp_path, width=1080, height=1920),
        tmp_path / "portrait.mp4",
        adapter=portrait,
        mode="preview",
        encoder="libx264",
        scale_max=540,
    )
    graph = portrait.commands[0][portrait.commands[0].index("-filter_complex") + 1]
    assert "scale=540:-2" in graph


def test_nvenc_runtime_failure_falls_back_and_marks_degraded(tmp_path: Path) -> None:
    class FlakyAdapter:
        def __init__(self) -> None:
            self.calls = 0
            self.commands: list[list[str]] = []

        def render(self, command: list[str], **kwargs: object) -> None:
            self.calls += 1
            if self.calls == 1:
                raise ExportError("h264_nvenc failed: openencodesessionex failed")
            self.commands.append(list(command))
            Path(command[-1]).write_bytes(b"mp4")

    adapter = FlakyAdapter()
    report: dict[str, object] = {}
    export_mp4(
        _state(tmp_path),
        tmp_path / "fallback.mp4",
        adapter=adapter,
        mode="preview",
        encoder="h264_nvenc",
        scale_max=540,
        report=report,
    )
    assert report["encoder"] == "libx264"
    assert report["degraded"] is True
    assert report["degraded_reason"] == "nvenc_runtime_fallback"
    assert adapter.commands
    assert "libx264" in adapter.commands[-1]
    assert "h264_nvenc" not in adapter.commands[-1]


def test_video_export_preview_keeps_the_master(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_export(_state, destination, **kwargs):
        seen.update(kwargs)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(destination).write_bytes(b"preview")
        return Path(destination)

    monkeypatch.setattr(video_export, "render_master", fake_export)
    output = tmp_path / "out"
    master = output / "exports" / "youtube_master.mp4"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"master")
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        state=_state(tmp_path),
    )
    VideoExportStep().run(
        context,
        VideoExportParams(mode="preview"),
        StepIO(),
    )
    artifact = Path(context.artifacts["video"])
    assert artifact.name == "preview_fast.mp4"
    assert artifact.read_bytes() == b"preview"
    assert master.read_bytes() == b"master"
    assert seen["mode"] == "preview"
    assert context.metadata["video_export_mode"] == "preview"
    assert "video_export_elapsed_sec" in context.metadata


def test_delivery_bundle_preview_keeps_youtube_master(tmp_path: Path) -> None:
    class BundleAdapter:
        def render(self, command, progress=None):
            Path(command[-1]).write_bytes(b"fake-mp4")

    output = tmp_path / "project"
    master = output / "exports" / "youtube_master.mp4"
    master.parent.mkdir(parents=True)
    master.write_bytes(b"master")
    result = build_delivery_bundle(
        _state(tmp_path),
        output,
        request=DeliveryBundleRequest(
            targets=("mp4_youtube",),
            mp4_mode="preview",
        ),
        adapter=BundleAdapter(),
    )
    preview = Path(result["files"]["mp4"]["path"])
    assert preview.name == "preview_fast.mp4"
    assert preview.is_file()
    assert master.read_bytes() == b"master"
    assert result["files"]["mp4"]["mode"] == "preview"


def test_default_mode_is_final() -> None:
    assert VideoExportParams().mode == "final"
