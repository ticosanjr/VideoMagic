"""v4.8.0 QA validation, browser lookup, and multi-slot auto-select."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.curation_board import auto_select_board, publish_board
from videoflow.application.overlay_geometry import PixelBox, caption_box, collisions
from videoflow.application.projects import init_project
from videoflow.core.context import PipelineContext
from videoflow.domain.config import CaptionStyle
from videoflow.domain.errors import VideoFlowError
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    OverlayClip,
    ProjectState,
    Sentence,
    WordTiming,
)
from videoflow.domains.vision import browser
from videoflow.mcp_server.guard import error_envelope, mcp_tool_guard
from videoflow.steps.base import StepIO
from videoflow.steps.captions import (
    CaptionsPlanParams,
    CaptionsPlanStep,
    EmptyAssEventsError,
)


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


def test_caption_box_keeps_the_short_safe_zone_center() -> None:
    vertical = caption_box(CaptionStyle(), 1080, 1920)
    assert vertical.x == 140
    assert vertical.width == 800
    assert vertical.x + vertical.width // 2 == 540
    assert vertical.y + vertical.height // 2 == pytest.approx(1340, abs=2)

    square = caption_box(CaptionStyle(), 1080, 1350)
    assert square.x == 140
    assert square.width == 800
    assert square.bottom == 1350 - 189


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


def test_vf_qa_accepts_skip_off_and_rejects_unknown_modes(
    tmp_path: Path, monkeypatch
) -> None:
    from tests.unit.test_core_tools import setup

    tools, record, _ = setup(tmp_path, monkeypatch)
    skipped = tools["vf_qa"](project_id=record.project_id, mode="skip")
    assert skipped["ok"] is True
    assert skipped["status"] == "skipped"
    off = tools["vf_qa"](project_id=record.project_id, mode="off")
    assert off["ok"] is True
    invalid = tools["vf_qa"](project_id=record.project_id, mode="bogus")
    assert invalid["ok"] is False
    assert invalid["error_code"] == "invalid_qa_mode"


def test_captions_plan_fails_closed_when_ass_has_no_dialogue(
    tmp_path: Path, monkeypatch
) -> None:
    media = MediaInfo(
        source_path=str(tmp_path / "source.mp4"),
        duration_frames=60,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48_000,
    )
    (tmp_path / "source.mp4").write_bytes(b"source")
    sentence = Sentence(
        id=0,
        start_sample=9_600,
        end_sample=134_400,
        text="público, império, ação",
        words=[
            WordTiming(word="público,", start_sample=9_600, end_sample=50_000, probability=0.95),
            WordTiming(word="império,", start_sample=50_000, end_sample=90_000, probability=0.95),
            WordTiming(word="ação", start_sample=90_000, end_sample=134_400, probability=0.95),
        ],
    )
    state = ProjectState(
        media_info=media,
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=144_000,
                timeline_in_sample=0,
                timeline_out_sample=144_000,
            )
        ],
    )
    context = PipelineContext(
        source=tmp_path / "source.mp4",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=media,
        state=state,
        transcript=[sentence],
    )
    monkeypatch.setattr(
        "videoflow.steps.captions.build_ass_lines",
        lambda *args, **kwargs: "[Events]\n",
    )
    with pytest.raises(EmptyAssEventsError) as info:
        CaptionsPlanStep().run(context, CaptionsPlanParams(), StepIO())
    assert info.value.code == "empty_ass_events"
