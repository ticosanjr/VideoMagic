from __future__ import annotations

import time
from pathlib import Path

from videoflow.application import live_source
from videoflow.application.jobs import Job


def job(tmp_path: Path) -> Job:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    return Job(
        source=source,
        output=tmp_path / "out",
        options={},
    )


def test_compatible_source_plays_directly(tmp_path: Path, monkeypatch) -> None:
    manager = live_source.LiveSourceManager()
    monkeypatch.setattr(manager, "_probe", lambda *_: (True, "browser-compatible"))
    state = manager.status(job(tmp_path), height=720)
    assert state.status == "ready"
    assert state.url.endswith("/source/file")


def test_incompatible_source_builds_a_proxy(tmp_path: Path, monkeypatch) -> None:
    manager = live_source.LiveSourceManager()
    monkeypatch.setattr(manager, "_probe", lambda *_: (False, "unsupported codec"))

    def fake_render(self, args, **kwargs):
        Path(args[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(args[-1]).write_bytes(b"proxy")

    monkeypatch.setattr(live_source.FFmpegAdapter, "render", fake_render)
    current = job(tmp_path)
    started = manager.start(current, height=720)
    assert started.status in {"preparing", "ready"}
    for _ in range(100):
        state = manager.status(current, height=720)
        if state.status in {"ready", "failed"}:
            break
        time.sleep(0.01)
    assert state.status == "ready"
    assert state.url.endswith("/live-source/file")
    assert manager.file(current, height=720) is not None


def test_container_is_checked_before_direct_playback(tmp_path: Path, monkeypatch) -> None:
    import json
    import subprocess

    manager = live_source.LiveSourceManager()
    monkeypatch.setattr(live_source, "find_binary", lambda _name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        live_source.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            json.dumps(
                {
                    "format": {"format_name": "matroska,webm"},
                    "streams": [
                        {"codec_type": "video", "codec_name": "h264"},
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                }
            ),
            "",
        ),
    )
    compatible, reason = manager._probe_codecs(tmp_path / "source.mkv")
    assert compatible is False
    assert "webm-safe" in reason
