from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import compositor
from videoflow.application.projects import (
    get_project,
    init_project,
    load_project_state,
    project_uuid,
    save_project_state,
)
from videoflow.domain.errors import ExportError
from videoflow.domain.state import MediaInfo, OverlayClip, ProjectState, VideoSegment
from videoflow.domain.styles import StyleDefinition


def _project(tmp_path: Path) -> tuple[object, Path]:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    record, _state = init_project(
        project_id="compositor-test",
        name="Compositor",
        output=tmp_path / "out",
    )
    media = MediaInfo(
        source_path=str(source),
        duration_frames=300,
        fps_num=30,
        fps_den=1,
        width=1080,
        height=1920,
        audio_sample_rate=48000,
    )
    state = ProjectState(
        project_id=project_uuid(record.project_id),
        media_info=media,
        sources={"src1": media},
        primary_source_id="src1",
    )
    save_project_state(record, state, bump_revision=False)
    return record, source


def _fake(path: Path, payload: bytes = b"asset") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_depth_composite_adds_graphic_and_matte_layers(
    tmp_path: Path, monkeypatch
) -> None:
    record, source = _project(tmp_path)
    graphic = _fake(tmp_path / "graphic.webm")
    matte = _fake(tmp_path / "matte.webm")
    monkeypatch.setattr(compositor, "_trim_clip", lambda *args, **kwargs: source)
    monkeypatch.setattr(
        compositor, "_remove_background", lambda *args, **kwargs: {"output": str(matte)}
    )
    monkeypatch.setattr(
        compositor, "_render_graphic", lambda *args, **kwargs: {"output": str(graphic)}
    )

    result = compositor.depth_composite(
        record.project_id,
        "Nvidia no Brasil",
        1.0,
        3.0,
        style_props={"palette": ["#101114", "#ffcc4d"]},
    )

    assert result["ok"] is True
    assert [layer["z"] for layer in result["layers"]] == [10, 20]
    assert [layer["start_frame"] for layer in result["layers"]] == [30, 30]
    assert [layer["duration_frames"] for layer in result["layers"]] == [60, 60]
    state = load_project_state(get_project(record.project_id))
    assert len(state.overlays) == 2


def test_depth_composite_accepts_an_asset_and_validates_range(
    tmp_path: Path, monkeypatch
) -> None:
    record, source = _project(tmp_path)
    asset = _fake(tmp_path / "title.png")
    matte = _fake(tmp_path / "matte.webm")
    monkeypatch.setattr(compositor, "_trim_clip", lambda *args, **kwargs: source)
    monkeypatch.setattr(
        compositor, "_remove_background", lambda *args, **kwargs: {"output": str(matte)}
    )
    result = compositor.depth_composite(record.project_id, str(asset), 0.0, 2.0)
    assert result["graphic"] == str(asset)
    with pytest.raises(ExportError):
        compositor.depth_composite(record.project_id, str(asset), 2.0, 2.0)


def test_picture_in_picture_creates_rounded_overlay(
    tmp_path: Path, monkeypatch
) -> None:
    record, _source = _project(tmp_path)
    asset = _fake(tmp_path / "screen.png")
    mask = _fake(tmp_path / "mask.png")
    monkeypatch.setattr(compositor, "_asset_ratio", lambda path: 16 / 9)
    monkeypatch.setattr(compositor, "ensure_rounded_mask", lambda *args: mask)
    monkeypatch.setattr(
        compositor,
        "_rounded_clip",
        lambda asset, mask, target, width, height, duration: _fake(target),
    )

    result = compositor.picture_in_picture(
        record.project_id,
        str(asset),
        0.0,
        2.0,
        anchor="bottom_right",
        width_ratio=0.3,
    )

    assert result["ok"] is True
    assert result["overlay"]["z"] == 25
    assert result["overlay"]["anchor"] == "bottom_right"
    assert result["width"] % 2 == 0 and result["height"] % 2 == 0


def test_picture_in_picture_rejects_missing_asset(tmp_path: Path) -> None:
    record, _source = _project(tmp_path)
    with pytest.raises(ExportError):
        compositor.picture_in_picture(record.project_id, str(tmp_path / "nope.mp4"), 0, 1)


def test_parallax_uses_two_vision_layers(tmp_path: Path, monkeypatch) -> None:
    record, _source = _project(tmp_path)
    image = _fake(tmp_path / "photo.png")
    subject = _fake(tmp_path / "subject.png")
    graphic = _fake(tmp_path / "parallax.mp4")
    monkeypatch.setattr(
        compositor, "_remove_background", lambda *args, **kwargs: {"output": str(subject)}
    )
    monkeypatch.setattr(
        compositor, "_render_graphic", lambda *args, **kwargs: {"output": str(graphic)}
    )

    result = compositor.parallax(record.project_id, str(image), 1.0, 4.0)

    assert result["ok"] is True
    assert result["layers"] == 2
    assert result["overlay"]["z"] == 10
    assert result["overlay"]["width_ratio"] == 0.72


def test_parallax_rejects_non_image(tmp_path: Path) -> None:
    record, _source = _project(tmp_path)
    clip = _fake(tmp_path / "clip.mp4")
    with pytest.raises(ExportError):
        compositor.parallax(record.project_id, str(clip), 0.0, 1.0)


def test_style_preview_renders_a_vertical_card(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.style_catalog import StyleCatalog

    record, _source = _project(tmp_path)
    style = StyleDefinition(
        style_id="preview-style",
        name="Preview Style",
        aspect_ratio="9:16",
        palette=["#101114", "#ffcc4d", "#ffffff"],
        fonts=["Inter"],
        caption_preset="kinetic_highlight",
        layout_mode="cutout",
        hook_strategy="No Brasil ninguém te contou isso",
    )
    StyleCatalog().save(style)
    output = _fake(tmp_path / "preview.mp4")
    monkeypatch.setattr(
        compositor, "_render_graphic", lambda *args, **kwargs: {"output": str(output)}
    )

    result = compositor.style_preview(record.project_id, style.style_id, duration_sec=6)

    assert result["ok"] is True
    assert result["width"] == 540
    assert result["height"] == 960
    assert result["draft"] is True
    assert result["font"] == "Inter"
    assert result["palette"] == style.palette


def test_style_preview_unknown_style(tmp_path: Path) -> None:
    record, _source = _project(tmp_path)
    with pytest.raises(ExportError):
        compositor.style_preview(record.project_id, "missing-style")


def test_compositor_tools_are_registered_and_guard_errors(
    tmp_path: Path, monkeypatch
) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.engine.batch import BatchManager
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _source = _project(tmp_path)
    payload = {"ok": True, "path": str(tmp_path / "out.mp4")}
    monkeypatch.setattr(compositor, "depth_composite", lambda *args, **kwargs: payload)
    monkeypatch.setattr(compositor, "picture_in_picture", lambda *args, **kwargs: payload)
    monkeypatch.setattr(compositor, "parallax", lambda *args, **kwargs: payload)

    def fake_preview(project_id: str, style_id: str, **kwargs):
        if style_id == "missing":
            raise ExportError("unknown style")
        return payload

    monkeypatch.setattr(compositor, "style_preview", fake_preview)
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager, batch_manager=BatchManager(manager)),
    )

    assert tools["vf_depth_composite"](
        project_id=record.project_id,
        text_or_asset="title",
        start_sec=0.0,
        end_sec=1.0,
    )["ok"] is True
    assert tools["vf_pip"](
        project_id=record.project_id,
        overlay_asset="clip.mp4",
        start_sec=0.0,
        end_sec=1.0,
    )["ok"] is True
    assert tools["vf_parallax"](
        project_id=record.project_id,
        image_path="photo.png",
        start_sec=0.0,
        end_sec=1.0,
    )["ok"] is True
    assert tools["vf_style_preview"](
        project_id=record.project_id,
        style_id="preview-style",
    )["ok"] is True
    missing = tools["vf_style_preview"](project_id="nope", style_id="missing")
    assert missing["ok"] is False


def test_internal_helpers_handle_empty_state_and_collisions() -> None:
    empty = ProjectState()
    assert compositor._canvas(empty) == (1920, 1080)
    assert compositor._fps(empty) == 30.0
    assert compositor._preview_canvas(empty, "") == (1920, 1080, "16:9")
    overlay = OverlayClip(
        overlay_id="overlay-2",
        path="x.png",
        start_frame=0,
        duration_frames=1,
    )
    assert compositor._next_overlay_id([overlay]) == "overlay-3"


def test_run_ffmpeg_reports_missing_binary_and_stderr(monkeypatch) -> None:
    monkeypatch.setattr(compositor, "find_binary", lambda name: None)
    with pytest.raises(ExportError):
        compositor._run_ffmpeg(["ffmpeg", "-version"], what="probe")

    class Failed:
        returncode = 1
        stderr = "line one\nboom"

    monkeypatch.setattr(compositor, "find_binary", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(compositor.subprocess, "run", lambda *args, **kwargs: Failed())
    with pytest.raises(ExportError) as info:
        compositor._run_ffmpeg(["ffmpeg", "-version"], what="probe")
    assert info.value.stderr == "line one\nboom"
    assert "boom" in info.value.message


def test_vision_wrappers_normalize_backend_failures(monkeypatch) -> None:
    module = SimpleNamespace(
        remove_background=lambda *args, **kwargs: {"output": "matte.png"},
        render_motion_graphic=lambda *args, **kwargs: {"output": "graphic.webm"},
    )
    monkeypatch.setattr(compositor, "_vision_module", lambda: module)
    assert compositor._remove_background("p", Path("x"), is_video=True)["output"] == "matte.png"
    assert (
        compositor._render_graphic(
            "p",
            template_or_code="card.html",
            props={"text": "x"},
            duration=1.0,
            alpha=True,
            width=320,
            height=240,
        )["output"]
        == "graphic.webm"
    )
    with pytest.raises(ExportError):
        compositor._vision_call("render", lambda: {"ok": True})
    with pytest.raises(ExportError):
        compositor._vision_call("render", lambda: (_ for _ in ()).throw(RuntimeError("bad")))


def test_append_overlays_rejects_missing_media_and_asset(tmp_path: Path) -> None:
    record, _source = _project(tmp_path)
    with pytest.raises(ExportError, match="does not exist"):
        compositor._append_overlays(
            record.project_id,
            [{"path": tmp_path / "missing.webm", "start_sec": 0, "end_sec": 1}],
            reason="test",
        )
    empty = ProjectState(project_id=project_uuid(record.project_id))
    save_project_state(record, empty, bump_revision=False)
    with pytest.raises(ExportError, match="no media"):
        compositor._append_overlays(
            record.project_id,
            [{"path": tmp_path / "missing.webm", "start_sec": 0, "end_sec": 1}],
            reason="test",
        )


def test_pip_caps_tall_assets_and_requires_pillow(tmp_path: Path, monkeypatch) -> None:
    record, _source = _project(tmp_path)
    asset = _fake(tmp_path / "tall.png")
    monkeypatch.setattr(compositor, "_asset_ratio", lambda path: 4 / 9)
    monkeypatch.setattr(compositor, "ensure_rounded_mask", lambda *args: None)
    with pytest.raises(ExportError, match="Pillow"):
        compositor.picture_in_picture(record.project_id, str(asset), 0.0, 1.0)
    with pytest.raises(ExportError):
        compositor.picture_in_picture(record.project_id, str(asset), 1.0, 1.0)

    mask = _fake(tmp_path / "mask.png")
    monkeypatch.setattr(compositor, "ensure_rounded_mask", lambda *args: mask)
    monkeypatch.setattr(
        compositor,
        "_rounded_clip",
        lambda asset, mask, target, width, height, duration: _fake(target),
    )
    result = compositor.picture_in_picture(
        record.project_id,
        str(asset),
        0.0,
        1.0,
        width_ratio=0.9,
    )
    assert result["height"] <= 1920 * 0.9
    cached = compositor.picture_in_picture(
        record.project_id,
        str(asset),
        0.0,
        1.0,
        width_ratio=0.9,
    )
    assert cached["asset"] == result["asset"]


def test_parallax_rejects_bad_range_and_missing_image(tmp_path: Path) -> None:
    record, _source = _project(tmp_path)
    image = _fake(tmp_path / "photo.png")
    with pytest.raises(ExportError):
        compositor.parallax(record.project_id, str(image), 1.0, 1.0)
    with pytest.raises(ExportError, match="does not exist"):
        compositor.parallax(record.project_id, str(tmp_path / "missing.png"), 0.0, 1.0)


def test_vision_module_is_available() -> None:
    module = compositor._vision_module()
    assert hasattr(module, "remove_background")
    assert hasattr(module, "render_motion_graphic")


def test_trim_clip_validates_media_and_range(tmp_path: Path) -> None:
    record, _source = _project(tmp_path)
    state = load_project_state(get_project(record.project_id))
    empty = ProjectState(project_id=project_uuid(record.project_id))
    with pytest.raises(ExportError, match="no media"):
        compositor._trim_clip(record.project_id, empty, 0.0, 1.0)
    assert state.media_info is not None
    offline = state.model_copy(
        update={
            "media_info": state.media_info.model_copy(
                update={"source_path": str(tmp_path / "missing.mp4")}
            )
        }
    )
    with pytest.raises(ExportError, match="offline"):
        compositor._trim_clip(record.project_id, offline, 0.0, 1.0)
    with pytest.raises(ExportError, match="50 ms"):
        compositor._trim_clip(record.project_id, state, 1.0, 1.0)


def test_asset_ratio_falls_back_on_bad_probe(monkeypatch) -> None:
    monkeypatch.setattr(compositor, "find_binary", lambda name: None)
    assert compositor._asset_ratio(Path("x.mp4")) == 16 / 9

    class Probe:
        returncode = 0
        stdout = "width=bad\nheight=2\n"
        stderr = ""

    monkeypatch.setattr(compositor, "find_binary", lambda name: "ffprobe")
    monkeypatch.setattr(compositor.subprocess, "run", lambda *args, **kwargs: Probe())
    assert compositor._asset_ratio(Path("x.mp4")) == 16 / 9


def test_style_frame_extracts_caches_and_handles_missing_media(
    tmp_path: Path, monkeypatch
) -> None:
    record, source = _project(tmp_path)
    state = load_project_state(get_project(record.project_id))
    state = state.model_copy(
        update={
            "video_segments": [
                VideoSegment(
                    clip_id="c1",
                    source_in_frame=30,
                    source_out_frame=60,
                    timeline_in_frame=0,
                    timeline_out_frame=30,
                )
            ]
        }
    )
    work = tmp_path / "work"
    work.mkdir()

    class Done:
        returncode = 0
        stderr = ""

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"png")
        return Done()

    monkeypatch.setattr(compositor.subprocess, "run", fake_run)
    frame = compositor._style_frame(state, work, 320, 240)
    assert frame is not None and frame.is_file()

    def should_not_run(*args, **kwargs):
        raise AssertionError("cached frame should not rerun FFmpeg")

    monkeypatch.setattr(compositor.subprocess, "run", should_not_run)
    assert compositor._style_frame(state, work, 320, 240) == frame

    empty = ProjectState(project_id=project_uuid(record.project_id))
    assert compositor._style_frame(empty, work, 320, 240) is None
    assert state.media_info is not None
    offline = state.model_copy(
        update={
            "media_info": state.media_info.model_copy(
                update={"source_path": str(tmp_path / "missing.mp4")}
            )
        }
    )
    assert compositor._style_frame(offline, work, 320, 240) is None
    monkeypatch.setattr(compositor, "find_binary", lambda name: None)
    assert compositor._style_frame(state, work, 640, 480) is None

    html = compositor._style_html(
        style_name="Style",
        style_id="style",
        layout="cutout",
        caption="hello",
        width=320,
        height=240,
        palette=["#101114", "#ffcc4d"],
        font="Inter",
        duration=1.0,
        background_image=source,
    )
    assert "background-image" in html
