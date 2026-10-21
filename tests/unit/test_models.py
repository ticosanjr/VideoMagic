"""Optional model catalog tests."""

from __future__ import annotations

from pathlib import Path

from videoflow.application import models


def test_catalog_lists_both_optional_models(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    listed = models.list_models()
    assert {item["id"] for item in listed} == {
        "faster-whisper-small",
        "whisper-tiny",
    }
    assert all(item["installed"] is False for item in listed)


def test_install_refuses_unknown_model(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    try:
        models.install_model("missing")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", "") == "state_not_ready"
    else:
        raise AssertionError("expected an unknown-model failure")
