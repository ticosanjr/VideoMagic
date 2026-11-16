"""Resolve adapter capability detection and push/pull mapping."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from videoflow.adapters import resolve


class FakeTimeline:
    def GetName(self) -> str:
        return "VideoFlow"

    def GetMarkers(self) -> dict:
        return {12: {"color": "Blue", "name": "cut", "note": "", "duration": 1}}

    def GetItemListInTrack(self, track_type: str, index: int) -> list:
        if track_type == "video" and index == 1:
            return [SimpleNamespace(GetName=lambda: "clip", GetStart=lambda: 0, GetEnd=lambda: 30)]
        return []


class FakeProject:
    def GetName(self) -> str:
        return "Demo"

    def GetMediaPool(self):
        return SimpleNamespace(ImportTimelineFromFile=lambda path, options: FakeTimeline())

    def GetCurrentTimeline(self):
        return FakeTimeline()


def fake_module():
    resolve_app = SimpleNamespace(
        GetProductName=lambda: "DaVinci Resolve Studio",
        GetVersionString=lambda: "20.0",
        GetProjectManager=lambda: SimpleNamespace(GetCurrentProject=lambda: FakeProject()),
    )
    return SimpleNamespace(scriptapp=lambda name: resolve_app)


def test_resolve_status_and_roundtrip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "DaVinciResolveScript", fake_module())
    status = resolve.resolve_status()
    assert status["available"] is True
    assert status["project"] == "Demo"

    from videoflow.core.context import PipelineContext
    from videoflow.domain.state import MediaInfo, ProjectState

    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=320,
        height=240,
        audio_sample_rate=48000,
    )
    context = PipelineContext(
        source=source,
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
        media=media,
        state=ProjectState(media_info=media),
    )
    pushed = resolve.resolve_roundtrip(
        context, direction="push", path=str(tmp_path / "timeline.fcpxml"), apply=False
    )
    assert pushed["ok"] is True
    assert pushed["timeline"] == "VideoFlow"

    pulled = resolve.resolve_roundtrip(context, direction="pull", path="", apply=False)
    assert pulled["markers"][0]["name"] == "cut"
    assert pulled["clips"][0]["name"] == "clip"
