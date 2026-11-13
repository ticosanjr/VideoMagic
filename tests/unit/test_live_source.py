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


def test_probe_errors_and_codec_rejections(tmp_path: Path, monkeypatch) -> None:
    import json
    import subprocess

    manager = live_source.LiveSourceManager()
    missing = tmp_path / "missing.mp4"
    assert str(manager._fingerprint(missing)) == str(missing)
    assert manager._probe(missing, 2000) == (
        False,
        "source height 2000px exceeds the live limit",
    )
    assert manager._probe(missing, 2000)[0] is False
    monkeypatch.setattr(live_source, "find_binary", lambda name: None)
    assert manager._probe_codecs(missing) == (False, "ffprobe is unavailable")
    manager._compat.clear()

    monkeypatch.setattr(live_source, "find_binary", lambda name: "ffprobe")

    def boom(*args, **kwargs):
        raise OSError("no ffprobe")

    monkeypatch.setattr(live_source.subprocess, "run", boom)
    assert "could not probe" in manager._probe_codecs(missing)[1]

    monkeypatch.setattr(
        live_source.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "bad"),
    )
    assert manager._probe_codecs(missing)[1] == "ffprobe could not read the source"

    monkeypatch.setattr(
        live_source.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "not json", ""),
    )
    assert manager._probe_codecs(missing)[1] == "ffprobe returned invalid JSON"

    def payload(format_name, video, audio="aac"):
        return subprocess.CompletedProcess(
            ["ffprobe"],
            0,
            json.dumps(
                {
                    "format": {"format_name": format_name},
                    "streams": [
                        {"codec_type": "video", "codec_name": video},
                        {"codec_type": "audio", "codec_name": audio},
                    ],
                }
            ),
            "",
        )

    monkeypatch.setattr(
        live_source.subprocess, "run", lambda *args, **kwargs: payload("avi", "mpeg4")
    )
    assert "container avi" in manager._probe_codecs(missing)[1]
    monkeypatch.setattr(
        live_source.subprocess,
        "run", lambda *args, **kwargs: payload("mp4", "mpeg4")
    )
    assert "video codec mpeg4" in manager._probe_codecs(missing)[1]
    monkeypatch.setattr(
        live_source.subprocess,
        "run", lambda *args, **kwargs: payload("mp4", "h264", "pcm_s16le"),
    )
    assert "audio codec" in manager._probe_codecs(missing)[1]


def test_status_and_proxy_edge_cases(tmp_path: Path, monkeypatch) -> None:
    import json

    manager = live_source.LiveSourceManager()
    current = job(tmp_path)
    current.options = {"source": str(tmp_path / "missing.mp4")}
    assert manager.status(current).status == "failed"

    current.options = {}
    current.result = {"media": {"height": "bad"}}
    monkeypatch.setattr(manager, "_probe", lambda *args: (False, "bad codec"))
    assert manager.status(current).status == "missing"

    proxy = current.output / "work" / "live-source.mp4"
    manifest = current.output / "work" / "live-source.json"
    proxy.parent.mkdir(parents=True)
    proxy.write_bytes(b"proxy")
    manifest.write_text("{bad", encoding="utf-8")
    assert manager._proxy_ready(current) is False
    manifest.write_text(json.dumps({"fingerprint": manager._fingerprint(current.source)}))
    assert manager._proxy_ready(current) is True
    assert manager.file(current).is_symlink() is False

    manager._states[str(current.job_id)] = live_source.LiveSourceState(
        status="preparing"
    )
    assert manager.start(current).status == "preparing"
    manager._states[str(current.job_id)] = live_source.LiveSourceState(status="failed")
    assert manager.file(current) is None

    monkeypatch.setattr(
        live_source.FFmpegAdapter,
        "render",
        lambda self, args, **kwargs: (_ for _ in ()).throw(RuntimeError("encode failed")),
    )
    proxy.unlink()
    manifest.unlink()
    manager._states.pop(str(current.job_id), None)
    state = manager.start(current)
    for _ in range(100):
        state = manager.status(current)
        if state.status in {"ready", "failed"}:
            break
        time.sleep(0.01)
    assert state.status == "failed"
    assert "encode failed" in state.error
