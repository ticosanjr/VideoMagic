"""Optional model catalog tests."""

from __future__ import annotations

from pathlib import Path

from videoflow.application import models


def test_catalog_lists_both_optional_models(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    listed = models.list_models()
    assert {item["id"] for item in listed} == {
        "faster-whisper-small",
        "pyannote-diarization-3.1",
        "whisper-tiny",
    }
    assert all(item["installed"] is False for item in listed)
    assert {item["capability"] for item in listed} == {"asr", "diarization"}
    assert all("used_by" in item for item in listed)


def test_install_refuses_unknown_model(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    try:
        models.install_model("missing")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", "") == "state_not_ready"
    else:
        raise AssertionError("expected an unknown-model failure")


def test_pyannote_model_install_uses_huggingface(monkeypatch, tmp_path: Path) -> None:
    import sys
    import types

    monkeypatch.setenv("VIDEOFLOW_HOME", str(tmp_path))

    def snapshot_download(*, repo_id, local_dir, token):
        target = Path(local_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "config.yaml").write_text("pipeline: diarization\n")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        types.SimpleNamespace(snapshot_download=snapshot_download),
    )
    result = models.install_model("pyannote-diarization-3.1", allow_network=True)
    assert result["installed"] is True
    assert Path(str(result["path"]), "config.yaml").is_file()
