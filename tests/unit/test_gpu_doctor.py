from __future__ import annotations

from types import SimpleNamespace

from gpu_worker import doctor


def _settings() -> SimpleNamespace:
    return SimpleNamespace(ffmpeg_cmd="/bin/true", asr_model="large-v3-turbo")


def test_doctor_flags_missing_pkg_resources(monkeypatch) -> None:
    def fake_import(module: str):
        if module == "pkg_resources":
            return False, "", "ModuleNotFoundError: No module named 'pkg_resources'"
        if module == "ctranslate2":
            return False, "", "ModuleNotFoundError: No module named 'pkg_resources'"
        if module == "faster_whisper":
            return False, "", "ModuleNotFoundError: No module named 'pkg_resources'"
        return True, "1.0", ""

    monkeypatch.setattr(doctor, "_import_detail", fake_import)
    monkeypatch.setattr(doctor, "_model_present", lambda model: True)
    monkeypatch.setattr(
        doctor,
        "probe_nvenc",
        lambda ffmpeg: SimpleNamespace(
            available=True,
            to_dict=lambda: {"available": True},
        ),
    )
    doctor.clear_cache()
    report = doctor.dependency_report(_settings(), force=True)
    assert report["asr_ready"] is False
    assert "pkg_resources" in report["asr_error"]
    assert report["checks"]["pkg_resources"] is False


def test_doctor_ready_when_all_imports_succeed(monkeypatch) -> None:
    monkeypatch.setattr(
        doctor, "_import_detail", lambda module: (True, "1.0", "")
    )
    monkeypatch.setattr(doctor, "_model_present", lambda model: True)
    monkeypatch.setattr(
        doctor,
        "probe_nvenc",
        lambda ffmpeg: SimpleNamespace(
            available=True,
            to_dict=lambda: {"available": True},
        ),
    )
    doctor.clear_cache()
    report = doctor.dependency_report(_settings(), force=True)
    assert report["asr_ready"] is True
    assert report["asr_error"] == ""
    assert report["ok"] is True


def test_doctor_reports_missing_model(monkeypatch) -> None:
    monkeypatch.setattr(
        doctor, "_import_detail", lambda module: (True, "1.0", "")
    )
    monkeypatch.setattr(doctor, "_model_present", lambda model: False)
    monkeypatch.setattr(
        doctor,
        "probe_nvenc",
        lambda ffmpeg: SimpleNamespace(
            available=True,
            to_dict=lambda: {"available": True},
        ),
    )
    doctor.clear_cache()
    report = doctor.dependency_report(_settings(), force=True)
    assert report["asr_ready"] is True
    assert report["asr_model_ready"] is False
    assert "warmup" in report["asr_error"]


def test_windows_kit_pins_compatible_setuptools() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    requirements = (
        root / "src" / "videoflow" / "templates" / "windows" / "requirements-windows.txt"
    ).read_text(encoding="utf-8")
    assert "setuptools==80.9.0" in requirements
    wheels = root / "src" / "videoflow" / "templates" / "wheels" / "win"
    assert (wheels / "setuptools-80.9.0-py3-none-any.whl").is_file()
    assert not list(wheels.glob("setuptools-84*.whl"))


def test_doctor_detects_a_partial_onnxruntime(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_import_detail", lambda module: (True, "1.0", ""))
    monkeypatch.setattr(
        doctor,
        "_onnx_detail",
        lambda: (
            False,
            "1.20.2",
            "AttributeError: module 'onnxruntime' has no attribute 'SessionOptions'",
            [],
        ),
    )
    monkeypatch.setattr(doctor, "_model_present", lambda model: True)
    monkeypatch.setattr(
        doctor,
        "probe_nvenc",
        lambda ffmpeg: SimpleNamespace(
            available=True,
            to_dict=lambda: {"available": True},
        ),
    )
    doctor.clear_cache()
    report = doctor.dependency_report(_settings(), force=True)
    assert report["asr_ready"] is True
    assert report["asr_vad_ready"] is False
    assert "SessionOptions" in report["asr_vad_error"]
    assert report["checks"]["onnxruntime"] is False
    assert report["repair_hint"]
