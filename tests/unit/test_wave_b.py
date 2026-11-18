from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.captions import (
    CaptionLine,
    build_ass,
    build_ass_lines,
    caption_lines,
    shift_ass_text,
)
from videoflow.application.crop import crop_box, crop_filter, parse_aspect
from videoflow.application.media_integrity import validate_duration
from videoflow.application.shorts import ShortClip
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
    WordTiming,
)
from videoflow.steps.shorts_reframe import ReframeParams, ReframeStep
from videoflow.steps.video_export import VideoExportParams


def test_crop_geometry_uses_normalized_focus() -> None:
    box = crop_box(1920, 1080, aspect="9:16", fx=0.25, fy=0.5)
    assert box.width == 608
    assert box.height == 1080
    assert box.x == 328
    assert box.y == 0
    assert crop_filter(1080, 1920, fx=0.5, fy=0.5) == (
        "crop=1080:1920:round((iw-ow)*0.500000):round((ih-oh)*0.500000)"
    )
    assert parse_aspect("4:5") == (4, 5)
    with pytest.raises(ValueError):
        parse_aspect("bad")


def test_ass_wrap_tags_dedup_and_shift() -> None:
    style = CaptionStyle(
        keyword_highlight_enabled=True,
        keyword_words=["resultado"],
        word_timing="word",
        font_size=80,
    )
    lines = [
        CaptionLine(start=0.0, end=1.0, text="resultado final"),
        CaptionLine(start=1.0, end=2.0, text="resultado final"),
    ]
    ass = build_ass_lines(lines, style=style, width=1080, height=1920)
    assert "WrapStyle: 0" in ass
    assert "\\c&H" in ass
    assert "\\\\c&H" not in ass
    assert ass.count("[Events]") == 1
    assert "resultado final" not in ass.split("[Events]")[1] or ass.count("Dialogue:") == 1
    shifted = shift_ass_text(ass, 1.2)
    assert "0:00:01.20" in shifted

    long_line = CaptionLine(start=0, end=2, text=" ".join(["palavra"] * 30))
    wrapped = build_ass_lines([long_line], style=style, width=1080, height=1920)
    assert "\\N" in wrapped


def test_caption_dedup_across_cut_and_word_mode() -> None:
    sentence = Sentence(
        id=1,
        start_sample=0,
        end_sample=96000,
        text="uma frase inteira",
        words=[
            WordTiming(word="uma", start_sample=0, end_sample=24000, probability=1.0),
            WordTiming(word="frase", start_sample=24000, end_sample=48000, probability=1.0),
            WordTiming(word="inteira", start_sample=48000, end_sample=96000, probability=1.0),
        ],
    )
    lines = caption_lines(
        [sentence],
        [(0, 48000), (48000, 96000)],
        sample_rate=48000,
        word_timing="sentence",
    )
    assert len(lines) == 1
    assert lines[0].start == 0
    assert lines[0].end == 2.0


def test_reframe_static_fallback_emits_keyframes(tmp_path: Path) -> None:
    media = MediaInfo(
        source_path=str(tmp_path / "source.mp4"),
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    clip = ShortClip(
        title="Hook",
        start_sample=0,
        end_sample=48000,
        sentence_ids=(1,),
        pieces=((0, 48000),),
    )
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path,
        work=tmp_path / "work",
        exports=tmp_path / "exports",
        media=media,
        transcript=[Sentence(id=1, start_sample=0, end_sample=48000, text="hello")],
    )
    context.selected_shorts = [clip]
    ReframeStep().run(context, ReframeParams(), _io())
    keyframes = context.selected_shorts[0].crop_keyframes
    assert keyframes == ((0.0, 0.5), (1.0, 0.5))


def _io():
    from videoflow.steps.base import StepIO

    return StepIO()


def test_duration_gate_detects_drift(monkeypatch, tmp_path: Path) -> None:
    import videoflow.application.media_integrity as integrity

    monkeypatch.setattr(integrity, "probe_durations", lambda path: (10.2, 10.0, 10.0))
    report = validate_duration(tmp_path / "out.mp4", 10.0)
    assert report.ok is False
    assert "format" in report.reason

    monkeypatch.setattr(integrity, "probe_durations", lambda path: (10.05, 10.0, 10.04))
    report = validate_duration(tmp_path / "out.mp4", 10.0)
    assert report.ok is True


def test_crop_preview_tool_missing_source_and_invalid_aspect(tmp_path: Path) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Preview", output=tmp_path / "preview")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    assert tools["vf_crop_preview"](project_id=record.project_id)["ok"] is False
    assert (
        tools["vf_crop_preview"](
            project_id=record.project_id,
            aspect="bad",
        )["ok"]
        is False
    )
    assert tools["vf_export"](project_id=record.project_id, audio_source="bad")["ok"] is False


def test_vf_export_delegates_to_bundle(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, state = init_project(name="Export", output=tmp_path / "export")
    from videoflow.domain.state import AudioSegment, MediaInfo, VideoSegment

    media = MediaInfo(
        source_path=str(tmp_path / "source.mp4"),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    state = state.model_copy(
        update={
            "media_info": media,
            "sources": {"primary": media},
            "primary_source_id": "primary",
            "video_segments": [
                VideoSegment(
                    clip_id="v1",
                    source_id="primary",
                    source_in_frame=0,
                    source_out_frame=30,
                    timeline_in_frame=0,
                    timeline_out_frame=30,
                )
            ],
            "audio_segments": [
                AudioSegment(
                    clip_id="a1",
                    source_id="primary",
                    source_in_sample=0,
                    source_out_sample=48000,
                    timeline_in_sample=0,
                    timeline_out_sample=48000,
                )
            ],
        }
    )
    save_project_state(record, state, bump_revision=False)
    captured: dict[str, object] = {}

    def fake_bundle(state, output, *, request):
        captured["request"] = request
        return {"ok": True, "targets": list(request.targets), "files": {}}

    monkeypatch.setattr("videoflow.application.delivery_bundle.build_delivery_bundle", fake_bundle)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )
    result = tools["vf_export"](project_id=record.project_id, targets=["resolve"])
    assert result["ok"] is True
    assert result["targets"] == ["resolve"]
    assert captured["request"].audio_source == "mix"


def test_master_export_look_and_audio_paths(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import master_export

    output = tmp_path / "project"
    (output / "color").mkdir(parents=True)
    (output / "audio").mkdir(parents=True)
    (output / "color" / "filters.json").write_text('{"filters": ["eq=brightness=0.1"]}')
    (output / "audio" / "master-filters.json").write_text('{"filters": ["loudnorm=I=-16"]}')
    (output / "audio" / "master.wav").write_bytes(b"wav")
    (output / "audio" / "final.wav").write_bytes(b"final")
    lut = output / "look.cube"
    lut.write_bytes(b"cube")

    look = master_export.project_look(output)
    assert look.video_filters == ("eq=brightness=0.1",)
    assert look.audio_filters == ("loudnorm=I=-16",)
    mapped = master_export.look_from_mapping(
        output,
        {"lut_path": "look.cube", "grain_amount": 2, "grain_fps": 0, "video_filters": ["hue=s=0"]},
    )
    assert mapped.lut_path == "look.cube"
    assert mapped.grain_amount == 1.0
    assert mapped.grain_fps == 1.0
    assert mapped.video_filters == ("hue=s=0",)
    assert master_export.resolve_audio_master(output, "timeline") is None
    assert master_export.resolve_audio_master(output, "mix") == output / "audio" / "final.wav"
    assert master_export.resolve_audio_master(output, "master") == output / "audio" / "master.wav"
    assert master_export.resolve_audio_master(output, "unknown") == output / "audio" / "master.wav"

    captured: dict[str, object] = {}

    def fake_export(state, destination, **kwargs):
        captured.update(kwargs)
        Path(destination).write_bytes(b"mp4")
        return Path(destination)

    monkeypatch.setattr(master_export, "export_mp4", fake_export)
    master_export.render_master(
        object(),
        tmp_path / "out.mp4",
        output=output,
        audio_source="timeline",
        look=mapped,
        video_filters=["scale=1280:-2"],
        loudness_lufs=-16,
    )
    assert captured["video_filters"] == [
        "hue=s=0",
        f"lut3d=file='{lut}':interp=tetrahedral",
        "noise=alls=20:allf=t+u",
        "scale=1280:-2",
    ]
    assert captured["audio_filters"] == ["loudnorm=I=-16"]
    assert captured["audio_master"] is None


def test_crop_and_crop_preview_errors(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import crop_preview
    from videoflow.domain.errors import ExportError

    wide = crop_box(1080, 1920, aspect="16:9", fx=1.0, fy=1.0)
    assert wide.width == 1080
    assert wide.height == 608
    assert crop_filter(100, 100, fx=2, fy=-1).startswith("crop=100:100:round((iw-ow)*1.000000)")
    with pytest.raises(ValueError):
        parse_aspect("16x9")
    with pytest.raises(ValueError):
        parse_aspect("0:9")
    with pytest.raises(ValueError):
        crop_box(0, 10)

    with pytest.raises(ExportError):
        crop_preview.render_crop_preview(tmp_path / "missing.mp4", tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    monkeypatch.setattr(crop_preview, "find_binary", lambda name: None)
    with pytest.raises(ExportError):
        crop_preview.render_crop_preview(source, tmp_path)


def test_media_integrity_error_and_missing_paths(tmp_path: Path, monkeypatch) -> None:
    import videoflow.application.media_integrity as integrity
    from videoflow.domain.errors import ExportError

    monkeypatch.setattr(integrity, "find_binary", lambda name: None)
    with pytest.raises(ExportError):
        integrity.probe_durations(tmp_path / "out.mp4")

    monkeypatch.setattr(integrity, "find_binary", lambda name: "ffprobe")
    monkeypatch.setattr(
        integrity.subprocess,
        "run",
        lambda *args, **kwargs: __import__("types").SimpleNamespace(
            returncode=1, stderr="bad", stdout=""
        ),
    )
    with pytest.raises(ExportError):
        integrity.probe_durations(tmp_path / "out.mp4")

    monkeypatch.setattr(
        integrity.subprocess,
        "run",
        lambda *args, **kwargs: __import__("types").SimpleNamespace(
            returncode=0, stderr="", stdout="not-json"
        ),
    )
    with pytest.raises(ExportError):
        integrity.probe_durations(tmp_path / "out.mp4")

    monkeypatch.setattr(integrity, "probe_durations", lambda path: (None, None, None))
    assert integrity.validate_duration(tmp_path / "out.mp4", 1.0).ok is True
    monkeypatch.setattr(integrity, "probe_durations", lambda path: (2.0, 2.0, 2.0))
    with pytest.raises(ExportError):
        integrity.validate_or_raise(tmp_path / "out.mp4", 1.0)


def test_caption_edge_helpers(tmp_path: Path) -> None:
    from videoflow.application.captions import (
        _merge_caption_lines,
        _wrap_ass_markup,
        build_ass,
        shift_ass_file,
    )

    assert "[Events]" in build_ass([])
    assert shift_ass_text("plain", 1.0) == "plain"
    assert shift_ass_text("plain", 0.0) == "plain"
    merged = _merge_caption_lines(
        [
            CaptionLine(start=0, end=2, text="same"),
            CaptionLine(start=1, end=3, text="same"),
        ]
    )
    assert len(merged) == 1
    assert merged[0].end == 3
    wrapped = _wrap_ass_markup("word " * 30, CaptionStyle(font_size=80), 320)
    assert "\\N" in wrapped
    source = tmp_path / "captions.ass"
    source.write_text("[Events]\n", encoding="utf-8")
    target = shift_ass_file(source, 1.0, tmp_path / "shifted.ass")
    assert target.is_file()


def test_video_export_missing_lut_and_mix(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps.video_export import VideoExportStep

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
    with pytest.raises(Exception, match="mixed audio"):
        VideoExportStep().run(
            context,
            VideoExportParams(filename_mode="fixed", filename="out.mp4", audio_source="mix"),
            _io(),
        )


def test_caption_and_crop_edge_branches(tmp_path: Path) -> None:
    from videoflow.application.captions import merge_ass_files

    with pytest.raises(ValueError):
        parse_aspect("a:b")
    assert parse_aspect("1:1") == (1, 1)
    assert build_ass_lines([CaptionLine(start=1, end=0, text="bad")], width=320, height=240)
    assert _wrap_open_tag("x {open") is not None

    target = tmp_path / "empty.ass"
    merge_ass_files([], target)
    assert target.read_text() == ""
    assert build_ass([]).startswith("[Script Info]")


def _wrap_open_tag(text: str) -> str:
    from videoflow.application.captions import _wrap_ass_markup

    return _wrap_ass_markup(text, CaptionStyle(), 320)


def test_video_export_missing_lut_warning(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps.video_export import VideoExportStep

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

    def fake_render(state, destination, **kwargs):
        Path(destination).write_bytes(b"video")
        return Path(destination)

    monkeypatch.setattr("videoflow.steps.video_export.render_master", fake_render)
    VideoExportStep().run(
        context,
        VideoExportParams(
            filename_mode="fixed",
            filename="out.mp4",
            lut_path=str(tmp_path / "missing.cube"),
        ),
        _io(),
    )
    assert any("LUT not found" in item for item in context.warnings)


def test_export_mp4_classic_duration_fallback(tmp_path: Path, monkeypatch) -> None:
    import videoflow.exporters.mp4 as mp4

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=30,
                timeline_in_frame=0,
                timeline_out_frame=30,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
    )
    calls: list[list[str]] = []

    class FakeRenderer:
        def render(self, args):
            calls.append(list(args))
            Path(args[-1]).write_bytes(b"mp4")

    ok = type("Report", (), {"ok": True, "reason": ""})()
    bad = type("Report", (), {"ok": False, "reason": "drift"})()
    reports = iter([bad, ok])
    monkeypatch.setattr(mp4, "_duration_gate_enabled", lambda adapter: True)
    monkeypatch.setattr(mp4, "validate_duration", lambda *args, **kwargs: next(reports))
    mp4.export_mp4(state, tmp_path / "out.mp4", adapter=FakeRenderer())
    assert len(calls) == 2


def test_caption_dedupe_and_zero_line() -> None:
    style = CaptionStyle()
    line = CaptionLine(start=0, end=1, text="same")
    ass = build_ass_lines([line, line], style=style, width=320, height=240)
    assert ass.count("Dialogue:") == 1
    zero = build_ass_lines([CaptionLine(start=0, end=0, text="zero")], width=320)
    assert "zero" not in zero
    from videoflow.application.captions import _merge_caption_lines

    assert _merge_caption_lines([CaptionLine(start=0, end=0, text="zero")]) == []
    assert (
        _merge_caption_lines(
            [
                CaptionLine(start=0, end=2, text="same"),
                CaptionLine(start=1, end=1.5, text="same"),
            ]
        )[0].end
        == 2
    )


def test_crop_zero_aspect() -> None:
    assert parse_aspect("3:4") == (3, 4)
    with pytest.raises(ValueError):
        parse_aspect("1:0")


def test_crop_preview_ffmpeg_failure(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from videoflow.adapters import ffmpeg as ffmpeg_module
    from videoflow.application import crop_preview
    from videoflow.domain.errors import ExportError

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    monkeypatch.setattr(ffmpeg_module.FFmpegAdapter, "probe", lambda self, path: media)
    monkeypatch.setattr(
        crop_preview.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad"),
    )
    with pytest.raises(ExportError):
        crop_preview.render_crop_preview(source, tmp_path)


def test_video_export_cache_and_progress(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps.video_export import VideoExportStep

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

    def fake_render(state, destination, **kwargs):
        kwargs["progress"](50)
        Path(destination).write_bytes(b"video")
        return Path(destination)

    monkeypatch.setattr("videoflow.steps.video_export.render_master", fake_render)
    step = VideoExportStep()
    step.run(
        context,
        VideoExportParams(filename_mode="fixed", filename="out.mp4"),
        _io(),
    )
    path = Path(context.artifacts["video"])
    assert step.cache_outputs(context) == (path,)
    context.artifacts.pop("video")
    assert step.cache_outputs(context) == ()
    assert step.is_cacheable(VideoExportParams(filename_mode="fixed")) is True
    assert step.is_cacheable(VideoExportParams(filename_mode="source_timestamp")) is False
