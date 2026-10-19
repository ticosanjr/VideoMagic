import sys
from pathlib import Path

from videoflow import runtime


def test_environment_overrides(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_FFMPEG", "/custom/ffmpeg")
    assert runtime.portable_home() == tmp_path / "home"
    assert runtime.find_binary("ffmpeg") == "/custom/ffmpeg"


def test_ensure_home_creates_the_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "data"))
    assert runtime.ensure_home().is_dir()


def test_frozen_home_sits_next_to_the_executable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VIDEOWFLOW_HOME", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime, "executable_dir", lambda: tmp_path / "bin")
    assert runtime.portable_home() == tmp_path / "bin" / "videoflow-data"


def test_ui_dir_uses_the_environment_override(monkeypatch, tmp_path: Path) -> None:
    build = tmp_path / "ui"
    build.mkdir()
    (build / "index.html").write_text("ok", encoding="utf-8")
    monkeypatch.setenv("VIDEOWFLOW_UI_DIR", str(build))
    assert runtime.ui_dir() == build


def test_find_binary_prefers_a_vendored_copy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VIDEOWFLOW_FFMPEG", raising=False)
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    binary = vendor / "ffmpeg"
    binary.write_text("x", encoding="utf-8")
    assert runtime.find_binary("ffmpeg") == str(binary)
