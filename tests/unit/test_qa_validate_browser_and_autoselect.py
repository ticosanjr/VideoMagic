"""v4.8.0 QA validation, browser lookup, and multi-slot auto-select."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.curation_board import auto_select_board, publish_board
from videoflow.application.overlay_geometry import PixelBox, collisions
from videoflow.application.projects import init_project
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.state import MediaInfo, OverlayClip, ProjectState
from videoflow.domains.vision import browser
from videoflow.mcp_server.guard import error_envelope, mcp_tool_guard


def test_vf_export_validate_uses_the_absolute_exports_directory(
    tmp_path: Path, monkeypatch
) -> None:
    from tests.unit.test_core_tools import setup

    tools, record, _ = setup(tmp_path, monkeypatch)
    captured: dict[str, Path] = {}

    def fake_validate(path, **_kwargs):
        captured["path"] = Path(path)
        return {"ok": True, "exports": {}}

    monkeypatch.setattr(
        "videoflow.application.nle_validation.validate_nle_exports",
        fake_validate,
    )

    payload = tools["vf_export"](action="validate", project_id=record.project_id)

    expected = (Path(record.output).expanduser() / "exports").resolve()
    assert payload["ok"] is True
    assert payload["directory"] == str(expected)
    assert captured["path"] == expected
    assert captured["path"].is_absolute()


def test_guard_never_returns_an_empty_message() -> None:
    @mcp_tool_guard
    def fail() -> dict[str, object]:
        raise RuntimeError("")

    payload = fail()
    assert payload["ok"] is False
    assert payload["error_code"] == "runtimeerror"
    assert payload["message"].startswith("RuntimeError at ")
    assert payload["message"] != ":"
    assert payload["last_frame"]
    assert payload["stack_tail"]

    class Blank(VideoFlowError):
        code = "blank_error"

    envelope = error_envelope(Blank(""))
    assert envelope["error_code"] == "blank_error"
    assert envelope["message"].startswith("Blank at ")
    assert envelope["last_frame"]


def _state_with_overlay(z: int, *, anchor: str = "fullscreen") -> ProjectState:
    media = MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=1920,
        height=1080,
        audio_sample_rate=48000,
    )
    return ProjectState(
        media_info=media,
        overlays=[
            OverlayClip(
                overlay_id="br_01",
                path="/tmp/broll.mp4",
                start_frame=0,
                duration_frames=60,
                anchor=anchor,  # type: ignore[arg-type]
                width_ratio=1.0,
                z=z,
                kind="video",
            )
        ],
    )


def test_fullscreen_broll_behind_captions_is_not_a_collision() -> None:
    caption = PixelBox(x=0, y=980, width=1920, height=100, z=40)
    issues = collisions(
        _state_with_overlay(10),
        1920,
        1080,
        caption=caption,
    )
    assert not [item for item in issues if item["kind"] == "caption_overlap"]

    foreground = collisions(
        _state_with_overlay(50),
        1920,
        1080,
        caption=caption,
    )
    assert [item for item in foreground if item["kind"] == "caption_overlap"]


def test_browser_finds_edge_chrome_and_playwright_on_windows(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(browser, "_is_windows", lambda: True)
    monkeypatch.setattr(browser.commands, "resolve_binary", lambda *a, **k: None)
    program_files = tmp_path / "Program Files"
    program_files_x86 = tmp_path / "Program Files (x86)"
    local_app = tmp_path / "AppData" / "Local"
    monkeypatch.setenv("PROGRAMFILES", str(program_files))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(program_files_x86))
    monkeypatch.setenv("LOCALAPPDATA", str(local_app))

    edge = program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_bytes(b"edge")
    assert browser._chrome() == str(edge)

    edge.unlink()
    chrome = local_app / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"chrome")
    assert browser._chrome() == str(chrome)

    chrome.unlink()
    playwright = (
        local_app
        / "ms-playwright"
        / "chromium-1234"
        / "chrome-win"
        / "chrome.exe"
    )
    playwright.parent.mkdir(parents=True)
    playwright.write_bytes(b"chromium")
    assert browser._chrome() == str(playwright)


def _broll_items(project_output: Path) -> list[dict[str, object]]:
    media = project_output / "assets" / "curation"
    media.mkdir(parents=True, exist_ok=True)
    (media / "br_01.mp4").write_bytes(b"first")
    (media / "br_02.mp4").write_bytes(b"second")
    return [
        {
            "item_id": "br_01",
            "category": "broll",
            "title": "Opening",
            "media_type": "video",
            "local_path": "assets/curation/br_01.mp4",
            "start_sec": 27.37,
            "recommended": True,
        },
        {
            "item_id": "br_02",
            "category": "broll",
            "title": "Closing",
            "media_type": "video",
            "local_path": "assets/curation/br_02.mp4",
            "start_sec": 59.97,
            "recommended": True,
        },
    ]


def test_auto_select_keeps_multiple_broll_slots(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    record, _ = init_project(output=tmp_path / "project")
    publish_board(record.output, record.project_id, _broll_items(Path(record.output)))
    board = auto_select_board(record.output)
    selected = [item.item_id for item in board.items if item.status == "selected"]
    assert selected == ["br_01", "br_02"]

    items = _broll_items(Path(record.output))
    for item in items:
        item["recommended"] = False
    publish_board(record.output, record.project_id, items)
    automatic = auto_select_board(record.output)
    picked = [item.item_id for item in automatic.items if item.status == "selected"]
    assert picked == ["br_01", "br_02"]


@pytest.mark.parametrize("name", ["msedge.exe", "chrome.exe"])
def test_windows_candidates_include_the_standard_paths(name: str, monkeypatch) -> None:
    monkeypatch.setattr(browser, "_is_windows", lambda: True)
    monkeypatch.setenv("PROGRAMFILES", r"C:\Program Files")
    monkeypatch.setenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\me\AppData\Local")
    paths = [str(path) for path in browser._windows_candidates()]
    assert any(path.endswith(name) for path in paths)
