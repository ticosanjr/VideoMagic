import os
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


def test_find_whisper_binary_and_model(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VIDEOWFLOW_WHISPER_BIN", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_WHISPER_MODEL", raising=False)
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "executable_dir", lambda: tmp_path / "bin")
    whisper = tmp_path / "whisper"
    whisper.mkdir()
    binary = whisper / ("whisper-cli.exe" if os.name == "nt" else "whisper-cli")
    model = whisper / "ggml-tiny.bin"
    binary.write_text("x", encoding="utf-8")
    model.write_bytes(b"model")
    assert runtime.find_whisper_binary() == str(binary)
    assert runtime.find_whisper_model() == model


def test_find_whisper_honours_environment_overrides(monkeypatch, tmp_path: Path) -> None:
    binary = tmp_path / "custom-whisper"
    model = tmp_path / "custom.bin"
    binary.write_text("x", encoding="utf-8")
    model.write_bytes(b"model")
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_BIN", str(binary))
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_MODEL", str(model))
    assert runtime.find_whisper_binary() == str(binary)
    assert runtime.find_whisper_model() == model
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_MODEL", str(tmp_path / "missing.bin"))
    assert runtime.find_whisper_model() is None


def test_find_silero_model_prefers_bundle_and_honours_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VIDEOWFLOW_SILERO_MODEL", raising=False)
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "executable_dir", lambda: tmp_path / "bin")
    model = tmp_path / "vendor" / "silero" / "silero_vad.onnx"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    assert runtime.find_silero_model() == model

    override = tmp_path / "custom.onnx"
    override.write_bytes(b"model")
    monkeypatch.setenv("VIDEOWFLOW_SILERO_MODEL", str(override))
    assert runtime.find_silero_model() == override
    monkeypatch.setenv("VIDEOWFLOW_SILERO_MODEL", str(tmp_path / "missing.onnx"))
    assert runtime.find_silero_model() is None


def test_find_faster_whisper_model_prefers_bundle_and_honours_override(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("VIDEOWFLOW_FASTER_WHISPER_MODEL", raising=False)
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "executable_dir", lambda: tmp_path / "bin")
    model = tmp_path / "faster-whisper" / "small"
    model.mkdir(parents=True)
    (model / "model.bin").write_bytes(b"model")
    (model / "config.json").write_text("{}", encoding="utf-8")
    assert runtime.find_faster_whisper_model("small") == model

    override = tmp_path / "custom"
    override.mkdir()
    (override / "model.bin").write_bytes(b"model")
    (override / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("VIDEOWFLOW_FASTER_WHISPER_MODEL", str(override))
    assert runtime.find_faster_whisper_model("small") == override
    assert runtime.expected_faster_whisper_model("small") == override
    monkeypatch.setenv("VIDEOWFLOW_FASTER_WHISPER_MODEL", str(tmp_path / "missing"))
    assert runtime.find_faster_whisper_model("small") is None


def test_expected_faster_whisper_model_uses_the_development_vendor_path(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("VIDEOWFLOW_FASTER_WHISPER_MODEL", raising=False)
    monkeypatch.setattr(runtime, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "is_frozen", lambda: False)
    assert runtime.expected_faster_whisper_model("small") == (
        tmp_path / "vendor" / "faster-whisper" / "small"
    )
