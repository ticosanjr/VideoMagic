from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from videoflow.application import scene_web
from videoflow.core.context import PipelineContext
from videoflow.domain.errors import ExportError
from videoflow.steps import scene_web as scene_steps
from videoflow.steps.base import StepIO
from videoflow.steps.scene_web import (
    ExportMasterParams,
    ExportMasterStep,
    SceneAssembleParams,
    SceneAssembleStep,
    SceneRenderParams,
    SceneRenderStep,
)


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir()
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def _scene(tmp_path: Path) -> dict:
    asset = tmp_path / "still.png"
    asset.write_bytes(b"png")
    return {
        "scene_id": "SCENE-0001",
        "unit_id": "UNIT-0001",
        "title": "Opening",
        "narration": "Hello world",
        "duration_sec": 4,
        "width": 1920,
        "height": 1080,
        "background": "#080B10",
        "accent": "#FF3B30",
        "text_color": "#F8FAFC",
        "layers": [
            {"type": "image", "path": str(asset), "text": ""},
            {"type": "lower_third", "text": "Card", "start_sec": 0.2},
        ],
    }


def test_scene_html_supports_assets_and_three(tmp_path: Path) -> None:
    html = scene_web.scene_html(_scene(tmp_path), three_js=True)
    assert "threeSetTime" in html
    assert "import * as THREE" in html
    assert "window.setTime" in html
    assert "Card" in html
    assert "file://" in html


def test_scene_html_falls_back_to_plain_values(tmp_path: Path) -> None:
    html = scene_web.scene_html({"scene_id": "S", "background": "bad", "accent": "", "layers": []})
    assert "#080B10" in html
    assert "import * as THREE" not in html
    assert '<canvas id="three-canvas">' not in html


def test_write_scene_html_and_manifest(tmp_path: Path) -> None:
    target = scene_web.write_scene_html(_scene(tmp_path), tmp_path / "code", title_style="center")
    assert target.is_file()
    manifest = scene_web.write_manifest(tmp_path / "motion", [_scene(tmp_path)])
    assert json.loads(manifest.read_text())["count"] == 1


def test_concatenate_and_mux_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(scene_web, "find_binary", lambda name: "ffmpeg")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if "-show_entries" in command:
            return SimpleNamespace(returncode=0, stderr="", stdout="1.0\n")
        target = Path(command[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"media")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(scene_web.subprocess, "run", fake_run)
    first = tmp_path / "one.mp4"
    first.write_bytes(b"1")
    target = tmp_path / "joined.mp4"
    assert scene_web.concatenate([first], target) == target
    subtitles = tmp_path / "captions.ass"
    subtitles.write_text("x", encoding="utf-8")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"a")
    master = tmp_path / "master.mp4"
    assert scene_web.mux_master(first, audio, master, subtitles=subtitles) == master
    assert any("ass=" in item for command in commands for item in command)


def test_concatenate_rejects_empty_and_failures(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(RuntimeError):
        scene_web.concatenate([], tmp_path / "x.mp4")
    monkeypatch.setattr(scene_web, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        scene_web.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    first = tmp_path / "one.mp4"
    first.write_bytes(b"1")
    with pytest.raises(RuntimeError, match="assemble"):
        scene_web.concatenate([first], tmp_path / "x.mp4")


def test_render_scene_ffmpeg_delegates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        scene_web,
        "render_scene",
        lambda scene, output, **kwargs: Path(output) / "x.mp4",
    )
    assert scene_web.render_scene_ffmpeg({"scene_id": "S"}, tmp_path) == tmp_path / "x.mp4"


def test_render_html_scene_cleans_up_on_failure(tmp_path: Path, monkeypatch) -> None:
    class Playwright:
        def __enter__(self):
            raise RuntimeError("no browser")

        def __exit__(self, *args):
            return False

    module = ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: Playwright()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(scene_web, "find_binary", lambda name: "ffmpeg")
    (tmp_path / "scene.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(RuntimeError):
        scene_web.render_html_scene(
            tmp_path / "scene.html",
            tmp_path / "scene.mp4",
            duration_sec=1,
            fps=1,
            width=320,
            height=180,
        )


def test_scene_render_falls_back_to_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    (context.output / "motion").mkdir(parents=True)
    (context.output / "motion" / "scenes.json").write_text(
        json.dumps({"scenes": [_scene(tmp_path)]}), encoding="utf-8"
    )

    def fake_render(scene, output, **kwargs):
        target = Path(output) / "SCENE-0001.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mp4")
        return target

    monkeypatch.setattr(scene_steps, "render_scene_ffmpeg", fake_render)
    SceneRenderStep().run(
        context, SceneRenderParams(engine="ffmpeg", fps=1, max_scenes=1), StepIO()
    )
    manifest = json.loads((context.output / "motion" / "render-manifest.json").read_text())
    assert manifest["scenes"][0]["scene_id"] == "SCENE-0001"


def test_scene_render_tries_playwright_and_warns(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    (context.output / "motion").mkdir(parents=True)
    (context.output / "motion" / "scenes.json").write_text(
        json.dumps({"scenes": [_scene(tmp_path)]}), encoding="utf-8"
    )
    (context.output / "motion" / "code").mkdir(parents=True)
    (context.output / "motion" / "code" / "SCENE-0001.html").write_text("x")

    def fail_html(*args, **kwargs):
        raise RuntimeError("browser missing")

    def fake_render(scene, output, **kwargs):
        target = Path(output) / "SCENE-0001.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"mp4")
        return target

    monkeypatch.setattr(scene_steps, "render_html_scene", fail_html)
    monkeypatch.setattr(scene_steps, "render_scene_ffmpeg", fake_render)
    SceneRenderStep().run(context, SceneRenderParams(engine="playwright", fps=1), StepIO())
    assert any("headless render fallback" in item for item in context.warnings)


def test_scene_render_requires_scenes(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(ExportError):
        SceneRenderStep().run(context, SceneRenderParams(), StepIO())


def test_scene_assemble_and_export_master(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    (context.output / "motion").mkdir(parents=True)
    scene_file = context.output / "motion" / "SCENE-0001.mp4"
    scene_file.write_bytes(b"mp4")
    (context.output / "motion" / "render-manifest.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "scene_id": "SCENE-0001",
                        "path": str(scene_file),
                        "start_sec": 0,
                    }
                ]
            }
        )
    )
    audio = context.output / "audio" / "final.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"wav")
    context.artifacts["audio_mix"] = str(audio)

    monkeypatch.setattr(
        scene_steps,
        "concatenate",
        lambda paths, target: Path(target).write_bytes(b"joined") or target,
    )
    monkeypatch.setattr(
        scene_steps,
        "mux_master",
        lambda video, audio, target, subtitles=None: (
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            or Path(target).write_bytes(b"master")
            or target
        ),
    )
    SceneAssembleStep().run(context, SceneAssembleParams(), StepIO())
    assert Path(context.artifacts["video_draft"]).read_bytes() == b"master"

    ExportMasterStep().run(context, ExportMasterParams(), StepIO())
    assert Path(context.artifacts["video_master"]).is_file()
    assert Path(context.artifacts["master_report"]).is_file()


def test_scene_assemble_requires_audio(tmp_path: Path) -> None:
    context = _context(tmp_path)
    (context.output / "motion").mkdir(parents=True)
    scene_file = context.output / "motion" / "SCENE-0001.mp4"
    scene_file.write_bytes(b"mp4")
    (context.output / "motion" / "render-manifest.json").write_text(
        json.dumps({"scenes": [{"path": str(scene_file)}]})
    )
    with pytest.raises(ExportError, match="final audio"):
        SceneAssembleStep().run(context, SceneAssembleParams(), StepIO())


def test_scene_assignments_are_grouped_by_unit(tmp_path: Path) -> None:
    context = _context(tmp_path)
    path = context.output / "assets" / "assignments.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "assignments": [
                    {
                        "unit_id": "UNIT-0001",
                        "asset": {"downloaded_path": "/tmp/a.png", "kind": "image"},
                    }
                ]
            }
        )
    )
    assert scene_steps._assignments(context, "assets/assignments.json") == {
        "UNIT-0001": [{"path": "/tmp/a.png", "kind": "image"}]
    }


def test_scene_html_supports_video_layers(tmp_path: Path) -> None:
    asset = tmp_path / "clip.mp4"
    asset.write_bytes(b"mp4")
    html = scene_web.scene_html(
        {
            "scene_id": "S",
            "duration_sec": 2,
            "layers": [{"type": "video", "path": str(asset)}],
        }
    )
    assert '<video id="asset"' in html


def test_render_html_scene_with_fake_playwright(tmp_path: Path, monkeypatch) -> None:
    html_path = tmp_path / "scene.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    target = tmp_path / "scene.mp4"
    calls: list[str] = []

    class Page:
        def goto(self, uri):
            calls.append("goto")

        def wait_for_timeout(self, value):
            calls.append("wait")

        def evaluate(self, script, value):
            calls.append("evaluate")

        def screenshot(self, path):
            Path(path).write_bytes(b"png")

    class Browser:
        def new_page(self, viewport):
            return Page()

        def close(self):
            calls.append("close")

    class Chromium:
        def launch(self, **kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    module = ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: Playwright()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(scene_web, "find_binary", lambda name: "ffmpeg")
    monkeypatch.setattr(
        scene_web.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout=""),
    )
    rendered = scene_web.render_html_scene(
        html_path,
        target,
        duration_sec=1,
        fps=2,
        width=320,
        height=180,
    )
    assert rendered == target
    assert "close" in calls
    assert not (tmp_path / ".scene-frames").exists()

    monkeypatch.setattr(
        scene_web.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad", stdout=""),
    )
    with pytest.raises(RuntimeError, match="encode"):
        scene_web.render_html_scene(
            html_path,
            target,
            duration_sec=1,
            fps=1,
            width=320,
            height=180,
        )


def test_scene_helpers_require_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    module = ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: SimpleNamespace(  # type: ignore[attr-defined]
        __enter__=lambda self: self, __exit__=lambda self, *args: False
    )
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    monkeypatch.setattr(scene_web, "find_binary", lambda name: None)
    with pytest.raises(RuntimeError, match="FFmpeg"):
        scene_web.render_html_scene(
            tmp_path / "s.html", tmp_path / "s.mp4", duration_sec=1, fps=1, width=2, height=2
        )
    with pytest.raises(RuntimeError, match="FFmpeg"):
        scene_web.concatenate([tmp_path / "x.mp4"], tmp_path / "out.mp4")
    with pytest.raises(RuntimeError, match="FFmpeg"):
        scene_web.mux_master(tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "m.mp4")
