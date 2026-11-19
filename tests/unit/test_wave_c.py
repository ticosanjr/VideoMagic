from __future__ import annotations

import os
from pathlib import Path

import pytest

from videoflow.application import analysis_cache, disk, media_pool
from videoflow.application.beatmap_plan import build_beatmap_plan
from videoflow.application.masks import ensure_rounded_mask, mask_root
from videoflow.application.overlays import add_overlay
from videoflow.application.projects import (
    get_project,
    init_project,
    load_project_state,
    save_project_state,
)
from videoflow.application.qa_final import audit_final
from videoflow.application.shorts_batch import run_shorts_batch
from videoflow.application.style_catalog import StyleCatalog
from videoflow.application.style_compiler import apply_style, compile_style, validate_style
from videoflow.domain.errors import FilesystemError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    OverlayClip,
    ProjectState,
    Sentence,
    VideoSegment,
)
from videoflow.domain.styles import StyleDefinition


def _media(tmp_path: Path) -> MediaInfo:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    return MediaInfo(
        source_path=str(source),
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )


def _state(tmp_path: Path, *, transcript: bool = False) -> ProjectState:
    media = _media(tmp_path)
    return ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        transcript=[
            Sentence(
                id=1,
                start_sample=0,
                end_sample=48000,
                text="uma frase de teste",
            )
        ]
        if transcript
        else [],
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_id="primary",
                source_in_frame=0,
                source_out_frame=60,
                timeline_in_frame=0,
                timeline_out_frame=60,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_id="primary",
                source_in_sample=0,
                source_out_sample=96000,
                timeline_in_sample=0,
                timeline_out_sample=96000,
            )
        ],
    )


def test_rounded_mask_is_cached(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VF_CACHE_DIR", str(tmp_path / "cache"))
    first = ensure_rounded_mask(120, 80, 12)
    assert first is not None and first.is_file()
    second = ensure_rounded_mask(120, 80, 12)
    assert second == first
    assert first.parent == mask_root()


def test_filter_script_avoids_arg_max() -> None:
    from videoflow.adapters.ffmpeg import _filter_script_args

    small, small_dir = _filter_script_args(["ffmpeg", "-filter_complex", "null"])
    assert small_dir is None and "null" in small
    graph = "null" + ";" + "null" * 2000
    large, directory = _filter_script_args(["ffmpeg", "-filter_complex", graph, "-map", "0:v"])
    assert directory is not None
    assert "-filter_complex_script" in large
    assert Path(large[large.index("-filter_complex_script") + 1]).is_file()
    import shutil

    shutil.rmtree(directory, ignore_errors=True)


def test_analysis_cache_reads_and_writes(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setenv("VF_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        "videoflow.application.video_analysis.detect_scene_changes",
        lambda path: [1.0, 2.0],
    )
    assert analysis_cache.cached_scene_changes(source) == [1.0, 2.0]
    assert analysis_cache.cached_scene_changes(source) == [1.0, 2.0]
    monkeypatch.setattr(
        "videoflow.application.audio_analysis.detect_audio_energy",
        lambda path, rate: [(0, rate)],
    )
    assert analysis_cache.cached_audio_energy(source, 48000) == [(0, 48000)]
    assert analysis_cache.analysis_path(source).is_file()


def test_media_pool_and_disk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VF_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    pooled = media_pool.pool_file(source, kind="pcm")
    assert pooled.is_file()
    assert pooled.stat().st_ino == source.stat().st_ino
    assert media_pool.pool_file(pooled, kind="pcm") == pooled
    assert disk.free_gb(tmp_path) > 0
    with pytest.raises(FilesystemError):
        disk.ensure_free_space(tmp_path, min_free_gb=10**9)
    (tmp_path / "render" / "segments").mkdir(parents=True)
    assert disk.prune_render_segments(tmp_path)


def test_style_compiler_and_apply(tmp_path: Path) -> None:
    style = StyleDefinition(
        style_id="wave-c-style",
        name="Wave C",
        caption_preset="kinetic_highlight",
        layout_mode="cutout",
        motion_engine="ffmpeg",
        max_static_sec=2.5,
        min_silence_ms=300,
        target_lufs=-16.5,
    )
    assert validate_style(style)["ok"] is True
    compiled = compile_style(style)
    assert compiled["timeline"]["max_silence_ms"] == 300
    assert compiled["captions"]["preset"] == "kinetic_highlight"

    StyleCatalog().save(style)
    record, _ = init_project(name="Style", output=tmp_path / "style")
    state = _state(tmp_path, transcript=True)
    save_project_state(record, state, bump_revision=False)
    result = apply_style(record.project_id, style.style_id)
    assert result["ok"] is True
    assert result["beatmap_path"]
    loaded = load_project_state(get_project(record.project_id))
    assert loaded.style_id == style.style_id
    assert loaded.pipeline.applied_style_id == style.style_id


def test_beatmap_plan_overlay_and_qa(tmp_path: Path) -> None:
    state = _state(tmp_path, transcript=True)
    style = StyleDefinition(style_id="plan", name="Plan", caption_preset="clean_white")
    plan = build_beatmap_plan(state, style, instructions="keep it short")
    assert plan["captions"][0]["text"] == "uma frase de teste"
    assert plan["transitions"] == []

    record, _ = init_project(name="Overlay", output=tmp_path / "overlay")
    save_project_state(record, state, bump_revision=False)
    asset = tmp_path / "logo.png"
    asset.write_bytes(b"x")
    result = add_overlay(
        record.project_id,
        str(asset),
        at_timeline_sec=1.0,
        duration_sec=1.0,
        transition_in="fade",
    )
    assert result["ok"] is True
    assert load_project_state(get_project(record.project_id)).overlays[0].kind == "image"


def test_shorts_batch_with_fake_renderer(tmp_path: Path) -> None:
    record, _ = init_project(name="Batch", output=tmp_path / "batch")
    state = _state(tmp_path, transcript=True)
    save_project_state(record, state, bump_revision=False)

    class FakeRenderer:
        def render_short(self, source, pieces, destination, **kwargs):
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            Path(destination).write_bytes(b"short")
            return Path(destination)

    result = run_shorts_batch(
        record.project_id,
        [
            {
                "start_sec": 0,
                "end_sec": 1,
                "title": "One",
                "caption_preset": "tiktok_bold",
                "layout_mode": "full_screen",
            }
        ],
        adapter=FakeRenderer(),
    )
    assert result["ok"] is True
    assert Path(result["clips"][0]["path"]).is_file()
    assert Path(result["manifest"]).is_file()


def test_qa_final_advisory(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "master.mp4"
    video.write_bytes(b"video")
    state = _state(tmp_path)
    state = state.model_copy(
        update={
            "overlays": [
                OverlayClip(
                    overlay_id="o1",
                    path=str(tmp_path / "logo.png"),
                    start_frame=0,
                    duration_frames=10,
                    anchor="top_right",
                    margin_x=0,
                    margin_y=0,
                    width_ratio=0.2,
                )
            ]
        }
    )
    monkeypatch.setattr("videoflow.application.qa_final.detect_black", lambda path: [])
    monkeypatch.setattr("videoflow.application.qa_final.detect_freeze", lambda path: [])
    monkeypatch.setattr(
        "videoflow.application.qa_final.validate_integrity",
        lambda *args, **kwargs: type("R", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
    )
    monkeypatch.setattr(
        "videoflow.adapters.ffmpeg.FFmpegAdapter.measure_loudness",
        lambda self, path: {"integrated_lufs": -16.0, "true_peak_db": -1.0},
    )
    monkeypatch.setattr("videoflow.application.qa_final._contact_sheet", lambda video, target: None)
    report = audit_final(video, output=tmp_path, state=state)
    assert report["ok"] is True
    assert report["report"]
    assert any(item["kind"] == "safe_zone" for item in report["issues"])


def test_model_and_font_diagnostics(tmp_path: Path) -> None:
    from videoflow.application.fonts import font_available, register_font
    from videoflow.application.models import discover_model_files, model_diagnostics

    diagnostics = model_diagnostics()
    assert "catalog" in diagnostics and "search_paths" in diagnostics
    assert isinstance(discover_model_files(), list)
    assert font_available("") is True
    with pytest.raises(FilesystemError):
        register_font(tmp_path / "missing.ttf")
    assert os.path.isdir(tmp_path)


def test_wave_c_mcp_tools(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    style = StyleDefinition(
        style_id="wave-c-tools",
        name="Wave C tools",
        caption_preset="kinetic_highlight",
        layout_mode="cutout",
        motion_engine="ffmpeg",
    )
    StyleCatalog().save(style)
    record, _ = init_project(name="Tools", output=tmp_path / "tools")
    save_project_state(record, _state(tmp_path, transcript=True), bump_revision=False)
    asset = tmp_path / "asset.png"
    asset.write_bytes(b"x")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    assert tools["vf_style_validate"](style_id=style.style_id)["ok"] is True
    assert (
        tools["vf_style_apply"](project_id=record.project_id, style_id=style.style_id)["ok"] is True
    )
    assert (
        tools["vf_beatmap_plan"](project_id=record.project_id, style_id=style.style_id)["ok"]
        is True
    )
    assert (
        tools["vf_overlay"](
            project_id=record.project_id,
            asset_path=str(asset),
            at_timeline_sec=0.0,
            duration_sec=1.0,
        )["ok"]
        is True
    )
    monkeypatch.setattr(
        "videoflow.application.shorts_batch.run_shorts_batch",
        lambda *args, **kwargs: {"ok": True, "clips": [], "manifest": ""},
    )
    assert tools["vf_shorts_batch"](project_id=record.project_id, clips=[])["ok"] is True
    monkeypatch.setattr(
        "videoflow.application.qa_final.audit_final",
        lambda *args, **kwargs: {"ok": True, "issues": []},
    )
    assert tools["vf_qa_final"](project_id=record.project_id)["ok"] is True
    assert tools["vf_assets"](action="fonts")["ok"] is True
    assert tools["vf_assets"](action="unknown")["ok"] is False
    assert tools["vf_assets"](action="register_font")["ok"] is False
    assert tools["vf_capabilities"]()["ok"] is True


def test_core_new_tool_error_branches(tmp_path: Path) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Core edges", output=tmp_path / "core-edges")
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    assert tools["vf_style_validate"](style_id="missing")["ok"] is False
    assert tools["vf_style_apply"](project_id="missing", style_id="missing")["ok"] is False
    assert tools["vf_beatmap_plan"](project_id="missing")["ok"] is False
    assert tools["vf_overlay"](project_id="missing", asset_path="missing")["ok"] is False
    assert tools["vf_shorts_batch"](project_id="missing", clips=[])["ok"] is False
    assert tools["vf_qa_final"](project_id=record.project_id)["ok"] is False
    assert tools["vf_assets"](action="register_font")["ok"] is False
    assert tools["vf_assets"](action="register_font", font_path="missing")["ok"] is False
    assert tools["vf_capabilities"]()["ok"] is True


def test_segmented_repair_path(tmp_path: Path, monkeypatch) -> None:
    import videoflow.exporters.mp4 as mp4

    media = _media(tmp_path)
    video = [
        VideoSegment(
            clip_id=f"v{index}",
            source_id="primary",
            source_in_frame=0,
            source_out_frame=6,
            timeline_in_frame=index * 6,
            timeline_out_frame=(index + 1) * 6,
        )
        for index in range(20)
    ]
    audio = [
        AudioSegment(
            clip_id=f"v{index}",
            source_id="primary",
            source_in_sample=0,
            source_out_sample=9600,
            timeline_in_sample=index * 9600,
            timeline_out_sample=(index + 1) * 9600,
        )
        for index in range(20)
    ]
    state = ProjectState(
        media_info=media,
        sources={"primary": media},
        primary_source_id="primary",
        video_segments=video,
        audio_segments=audio,
    )

    class FakeRenderer:
        def render(self, args):
            Path(args[-1]).write_bytes(b"mp4")

    bad = type("Report", (), {"ok": False, "reason": "drift"})()
    good = type("Report", (), {"ok": True, "reason": ""})()
    reports = iter([bad, good])
    monkeypatch.setattr(mp4, "_duration_gate_enabled", lambda adapter: True)
    monkeypatch.setattr(mp4, "_integrity_report", lambda *args, **kwargs: next(reports))
    result = mp4.export_mp4(state, tmp_path / "repaired.mp4", adapter=FakeRenderer())
    assert result.is_file()


def test_style_validation_errors() -> None:
    bad = StyleDefinition(
        style_id="bad-style",
        name="Bad",
        caption_preset="does_not_exist",
        layout_mode="cutout",
        motion_engine="ffmpeg",
        fonts=["Definitely Missing Font"],
    )
    validation = validate_style(bad)
    assert validation["ok"] is False
    assert len(validation["errors"]) >= 2
    assert validation["fonts"]["missing"] == ["Definitely Missing Font"]


def test_media_pool_link_fallbacks(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"x")
    target = tmp_path / "target.bin"

    def fail_link(*args, **kwargs):
        raise OSError("cross-device")

    def fail_symlink(*args, **kwargs):
        raise OSError("no symlink")

    monkeypatch.setattr(media_pool.os, "link", fail_link)
    monkeypatch.setattr(media_pool.os, "symlink", fail_symlink)
    copied = media_pool.link_or_copy(source, target)
    assert copied.is_file()
    assert copied.read_bytes() == b"x"


def test_contact_sheet_optional(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application import qa_final

    monkeypatch.setattr(qa_final, "find_binary", lambda name: None)
    assert qa_final._contact_sheet(tmp_path / "v.mp4", tmp_path / "sheet.jpg") is None
    monkeypatch.setattr(qa_final, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        qa_final.subprocess,
        "run",
        lambda *args, **kwargs: type("Done", (), {"returncode": 1})(),
    )
    assert qa_final._contact_sheet(tmp_path / "v.mp4", tmp_path / "sheet.jpg") is None


def test_core_new_tool_value_errors(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Value errors", output=tmp_path / "value-errors")
    state = _state(tmp_path)
    save_project_state(record, state, bump_revision=False)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    monkeypatch.setattr(
        "videoflow.application.style_compiler.apply_style",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad style")),
    )
    assert tools["vf_style_apply"](project_id=record.project_id, style_id="x")["ok"] is False
    monkeypatch.setattr(
        "videoflow.application.beatmap_plan.build_beatmap_plan",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad plan")),
    )
    assert tools["vf_beatmap_plan"](project_id=record.project_id)["ok"] is False
    monkeypatch.setattr(
        "videoflow.application.overlays.add_overlay",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad overlay")),
    )
    assert tools["vf_overlay"](project_id=record.project_id, asset_path="x")["ok"] is False
    monkeypatch.setattr(
        "videoflow.application.shorts_batch.run_shorts_batch",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad batch")),
    )
    batch = tools["vf_shorts_batch"](project_id=record.project_id, clips=[])
    assert batch["ok"] is True
    waited = tools["vf_job"](
        action="wait",
        project_id=record.project_id,
        job_id=batch["job"]["job_id"],
        timeout_sec=10,
    )
    assert waited["ok"] is False


def test_vf_overlay_preview_crop_success_and_failure(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Crop tool", output=tmp_path / "crop-tool")
    save_project_state(record, _state(tmp_path), bump_revision=False)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    monkeypatch.setattr(
        "videoflow.application.crop_preview.render_crop_preview",
        lambda *args, **kwargs: {"ok": True, "path": str(tmp_path / "preview.jpg")},
    )
    assert tools["vf_overlay_preview"](action="crop", project_id=record.project_id)["ok"] is True
    monkeypatch.setattr(
        "videoflow.application.crop_preview.render_crop_preview",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad crop")),
    )
    assert tools["vf_overlay_preview"](action="crop", project_id=record.project_id)["ok"] is False


def test_vf_export_error_branches(tmp_path: Path) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    assert tools["vf_export"](project_id="missing")["ok"] is False


def test_core_export_success_font_and_list_filter(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project, save_project_state
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _ = init_project(name="Export success", output=tmp_path / "export-success")
    save_project_state(record, _state(tmp_path), bump_revision=False)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )
    monkeypatch.setattr(
        "videoflow.application.delivery_bundle.build_delivery_bundle",
        lambda state, output, *, request: {
            "ok": True,
            "targets": list(request.targets),
            "files": {},
        },
    )
    exported = tools["vf_export"](project_id=record.project_id, targets=["resolve"])
    assert exported["ok"] is True
    assert exported["targets"] == ["resolve"]
    listed = tools["vf_project"](action="list", status="active")
    assert listed["ok"] is True

    font = Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf")
    if font.is_file():
        registered = tools["vf_assets"](action="register_font", font_path=str(font))
        assert registered["ok"] is True


def test_adapter_helpers_and_filter_edges(tmp_path: Path, monkeypatch) -> None:
    from videoflow.adapters.ffmpeg import (
        FFmpegAdapter,
        _crop_expression,
        _cutout_graph,
        _filter_script_args,
        _piece_keyframes,
        _rate_value,
    )

    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "_run_json", lambda args: {"streams": []})
    assert adapter.is_vfr(tmp_path / "x.mp4") is False
    monkeypatch.setattr(
        adapter,
        "_run_json",
        lambda args: {
            "streams": [{"codec_type": "video", "r_frame_rate": None, "avg_frame_rate": None}]
        },
    )
    assert adapter.is_vfr(tmp_path / "x.mp4") is False

    monkeypatch.setattr(adapter, "_run", lambda args: "")
    monkeypatch.setattr(Path, "replace", lambda self, target: target)
    assert adapter.normalize_cfr(
        tmp_path / "source.mp4", tmp_path / "norm.mp4", fps_num=30, fps_den=1
    )
    assert adapter.build_proxy(tmp_path / "source.mp4", tmp_path / "proxy.mp4")

    commands: list[list[str]] = []
    monkeypatch.setattr(
        adapter, "_capture", lambda args, **kwargs: commands.append(args) or ("", "")
    )
    (tmp_path / "frames").mkdir()
    adapter.extract_frames(tmp_path / "source.mp4", tmp_path / "frames", max_frames=2)
    assert commands

    assert _filter_script_args(["ffmpeg", "-filter_complex"]) == (
        ["ffmpeg", "-filter_complex"],
        None,
    )
    mask = tmp_path / "mask.png"
    mask.write_bytes(b"x")
    graph = _cutout_graph(
        "null", 100, 100, corner_radius=0.1, margin=0.1, head_overlap=0.1, mask_path=mask
    )
    assert "alphamerge" in graph
    assert _rate_value("bad") == 0.0
    assert _crop_expression([(0.0, 0.5)]) == "0.5"
    assert len(_piece_keyframes([(0.0, 0.4), (1.0, 0.8)], 0, 48000, 48000)) >= 2


def test_pool_missing_source_and_qa_loudness_error(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application import media_pool, qa_final

    missing = tmp_path / "missing.wav"
    assert media_pool.pool_file(missing) == missing

    video = tmp_path / "master.mp4"
    video.write_bytes(b"v")
    state = _state(tmp_path)
    monkeypatch.setattr(qa_final, "detect_black", lambda path: [])
    monkeypatch.setattr(qa_final, "detect_freeze", lambda path: [])
    monkeypatch.setattr(
        qa_final,
        "validate_integrity",
        lambda *args, **kwargs: type("R", (), {"ok": True, "to_dict": lambda self: {"ok": True}})(),
    )
    monkeypatch.setattr(
        "videoflow.adapters.ffmpeg.FFmpegAdapter.measure_loudness",
        lambda self, path: (_ for _ in ()).throw(RuntimeError("no loudness")),
    )
    monkeypatch.setattr(qa_final, "_contact_sheet", lambda video, target: None)
    report = qa_final.audit_final(video, output=tmp_path, state=state)
    assert "error" in report["loudness"]
