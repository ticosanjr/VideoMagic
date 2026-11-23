"""Runtime locations, binary discovery, and app wiring."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow import runtime
from videoflow.api import app as app_module
from videoflow.api.app import create_app


def test_bundle_root_and_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert runtime.is_frozen() is False
    assert runtime.bundle_root().name == "VideoMagic"

    monkeypatch.delenv("VIDEOWFLOW_HOME", raising=False)
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(runtime, "executable_dir", lambda: tmp_path / "bin")
    assert runtime.bundle_root() == tmp_path
    assert runtime.portable_home() == tmp_path / "bin" / "videoflow-data"


def test_portable_home_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    assert runtime.portable_home() == tmp_path / "home"

    monkeypatch.delenv("VIDEOWFLOW_HOME")
    appimage = tmp_path / "VideoFlow.AppImage"
    monkeypatch.setenv("APPIMAGE", str(appimage))
    assert runtime.portable_home() == tmp_path / "videoflow-data"

    monkeypatch.delenv("APPIMAGE")
    monkeypatch.setattr(runtime, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime.Path, "home", lambda: tmp_path)
    assert runtime.portable_home() == tmp_path / ".videoflow"


def test_portable_home_avoids_read_only_appimage_mount(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("VIDEOWFLOW_HOME", raising=False)
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(runtime, "is_frozen", lambda: True)
    monkeypatch.setattr(runtime, "executable_dir", lambda: Path("/tmp/.mount_abc/usr/bin"))
    monkeypatch.setattr(runtime.Path, "home", lambda: tmp_path)
    assert runtime.portable_home() == tmp_path / ".videoflow"


def test_find_binary_resolution_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_FFMPEG", "/custom/ffmpeg")
    assert runtime.find_binary("ffmpeg") == "/custom/ffmpeg"

    monkeypatch.delenv("VIDEOWFLOW_FFMPEG")
    monkeypatch.setattr(
        "videoflow.application.settings.effective_ffmpeg", lambda _name: "/configured"
    )
    assert runtime.find_binary("ffmpeg") == "/configured"

    monkeypatch.setattr(
        "videoflow.application.settings.effective_ffmpeg",
        lambda _name: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(runtime.shutil, "which", lambda _name: None)
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "ffmpeg").write_bytes(b"bin")
    assert runtime.find_binary("ffmpeg") == str(vendor / "ffmpeg")

    monkeypatch.setattr(runtime.shutil, "which", lambda _name: "/system/ffmpeg")
    (vendor / "ffmpeg").unlink()
    assert runtime.find_binary("ffmpeg") is not None


def test_allowed_roots_prefers_environment_and_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    assert runtime.allowed_roots() == [tmp_path]

    monkeypatch.delenv("VIDEOWFLOW_ALLOWED_ROOTS")
    monkeypatch.setattr(
        "videoflow.application.settings.effective_roots",
        lambda: [str(tmp_path / "a"), str(tmp_path / "a")],
    )
    assert runtime.allowed_roots() == [tmp_path / "a", tmp_path / "a"]

    monkeypatch.setattr(
        "videoflow.application.settings.effective_roots",
        lambda: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    monkeypatch.setattr(runtime.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(runtime, "portable_home", lambda: tmp_path / "data")
    roots = runtime.allowed_roots()
    assert roots[0] == tmp_path / "home"
    assert roots[-1] == tmp_path / "data"


def test_whisper_and_silero_discovery(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_BIN", "/custom/whisper")
    assert runtime.find_whisper_binary() == "/custom/whisper"

    monkeypatch.delenv("VIDEOWFLOW_WHISPER_BIN")
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "executable_dir", lambda: tmp_path)
    assert runtime.find_whisper_binary() is None
    whisper = tmp_path / "whisper" / "whisper-cli"
    whisper.parent.mkdir()
    whisper.write_bytes(b"bin")
    assert runtime.find_whisper_binary() == str(whisper)

    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_MODEL", str(model))
    assert runtime.find_whisper_model() == model
    model.unlink()
    assert runtime.find_whisper_model() is None

    silero = tmp_path / "silero.onnx"
    silero.write_bytes(b"model")
    monkeypatch.setenv("VIDEOWFLOW_SILERO_MODEL", str(silero))
    assert runtime.find_silero_model() == silero
    silero.unlink()
    assert runtime.find_silero_model() is None


def test_faster_whisper_model_detection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.bin").write_bytes(b"x")
    (model / "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setenv("VIDEOWFLOW_FASTER_WHISPER_MODEL", str(model))
    assert runtime.find_faster_whisper_model("small") == model
    assert runtime.expected_faster_whisper_model("small") == model

    (model / "config.json").unlink()
    assert runtime.find_faster_whisper_model("small") is None


def test_ui_dir_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("VIDEOWFLOW_UI_DIR", str(ui))
    assert runtime.ui_dir() == ui

    monkeypatch.setenv("VIDEOWFLOW_UI_DIR", str(tmp_path / "missing"))
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path / "bundle")
    fallback = runtime.ui_dir()
    assert fallback != tmp_path / "missing"
    assert fallback is None or (fallback / "index.html").is_file()


def test_create_app_schedules_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("VIDEOWFLOW_BACKUP_ON_START", "1")
    monkeypatch.setattr(
        app_module, "scheduled_backup", lambda **_kwargs: calls.append("backup")
    )

    app = create_app(ui=None)

    assert calls == ["backup"]
    assert app.title == "VideoFlow"


def test_cache_and_version_headers(tmp_path: Path) -> None:
    ui = tmp_path / "ui"
    (ui / "_app" / "immutable").mkdir(parents=True)
    (ui / "_app" / "chunks").mkdir(parents=True)
    (ui / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (ui / "_app" / "immutable" / "app.js").write_text("x", encoding="utf-8")
    (ui / "_app" / "chunks" / "app.js").write_text("x", encoding="utf-8")
    client = TestClient(create_app(ui=ui))

    root = client.get("/")
    assert root.headers["cache-control"] == "no-store, max-age=0"
    assert root.headers["pragma"] == "no-cache"
    assert root.headers["x-videoflow-version"]

    immutable = client.get("/_app/immutable/app.js")
    assert immutable.headers["cache-control"] == "public, max-age=31536000, immutable"

    chunk = client.get("/_app/chunks/app.js")
    assert chunk.headers["cache-control"] == "no-cache"


def test_start_background_services(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    monkeypatch.setenv("VIDEOWFLOW_SERVICE_AUTOSTART", "1")
    monkeypatch.setattr(app_module, "autostart", lambda: calls.append("services"))
    monkeypatch.setattr(app_module, "stop_managed_services", lambda: calls.append("stop-services"))

    app = create_app(ui=None, start_publisher=True)
    with TestClient(app):
        pass

    assert {"services", "stop-services"} <= set(calls)


def test_writable_parent_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from videoflow.runtime import _writable_parent

    assert _writable_parent(tmp_path / "data") is True
    assert _writable_parent(Path("/tmp/.mount_abc/usr/bin/videoflow-data")) is False
    monkeypatch.setenv("APPDIR", "/opt/appdir")
    assert _writable_parent(Path("/opt/appdir/videoflow-data")) is False
    monkeypatch.setattr(runtime.os, "access", lambda *args: (_ for _ in ()).throw(OSError()))
    assert _writable_parent(tmp_path / "other") is False
