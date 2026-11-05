"""Optional model catalog tests."""

from __future__ import annotations

from pathlib import Path

from videoflow.application import models


def test_catalog_lists_both_optional_models(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_MODELS_DIR", str(tmp_path / "models"))
    listed = models.list_models()
    assert {
        "faster-whisper-small",
        "pyannote-diarization-3.1",
        "whisper-tiny",
    }.issubset({item["id"] for item in listed})
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


def test_models_are_found_in_external_or_portable_home(monkeypatch, tmp_path: Path) -> None:
    portable = tmp_path / "portable"
    external = tmp_path / "external"
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(portable))
    monkeypatch.setenv("VIDEOWFLOW_EXTERNAL_HOME", str(external))

    external_model = external / "models" / "whisper" / "ggml-tiny.bin"
    external_model.parent.mkdir(parents=True)
    external_model.write_bytes(b"external")
    assert models.installed_path("whisper-tiny") == external_model
    assert models.verify_model("whisper-tiny")["path"] == str(external_model)
    assert str(external / "models") in models.verify_model("whisper-tiny")["search_paths"]

    external_model.unlink()
    portable_model = portable / "models" / "whisper" / "ggml-tiny.bin"
    portable_model.parent.mkdir(parents=True)
    portable_model.write_bytes(b"portable")
    assert models.installed_path("whisper-tiny") == portable_model
    assert models.models_dir() == external / "models"


def test_models_dir_uses_persistent_home_without_explicit_override(
    monkeypatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "portable"))
    monkeypatch.delenv("VIDEOWFLOW_MODELS_DIR", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_EXTERNAL_HOME", raising=False)
    assert models.models_dir() == home / ".videoflow" / "models"


def test_large_v3_catalog_includes_preprocessor_and_json_vocabulary() -> None:
    entry = models.CATALOG["faster-whisper-large-v3"]
    names = {name for _url, name, _checksum in entry["files"]}
    assert {
        "config.json",
        "tokenizer.json",
        "vocabulary.json",
        "preprocessor_config.json",
        "model.bin",
    } <= names


def test_pyannote_model_install_uses_huggingface(monkeypatch, tmp_path: Path) -> None:
    import sys
    import types

    monkeypatch.setenv("VIDEOFLOW_HOME", str(tmp_path))
    monkeypatch.setenv("VIDEOWFLOW_MODELS_DIR", str(tmp_path / "models"))

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
