"""Local plugin discovery, sandboxing, loading, and enable toggles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application import plugins


def write_plugin(
    root: Path,
    plugin_id: str = "demo.plugin",
    *,
    entry: str = "plugin.py",
    enabled: bool = True,
    api_version: int = 1,
    manifest: dict[str, object] | None = None,
) -> Path:
    directory = root / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": plugin_id,
        "name": "Demo plugin",
        "entry": entry,
        "enabled": enabled,
        "api_version": api_version,
        "permissions": [],
    }
    if manifest is not None:
        payload = manifest
    (directory / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")
    (directory / entry).write_text("VALUE = 42\n", encoding="utf-8")
    return directory


def test_list_plugins_skips_invalid_entries(tmp_path: Path) -> None:
    root = plugins.plugins_dir()
    root.mkdir(parents=True)
    (root / "stray.txt").write_text("x", encoding="utf-8")
    (root / "no-manifest").mkdir()
    write_plugin(root, "good")
    write_plugin(root, "newer", api_version=2)
    bad = root / "bad"
    bad.mkdir()
    (bad / "plugin.json").write_text("{not json", encoding="utf-8")

    items = plugins.list_plugins()

    assert [item["id"] for item in items] == ["good"]
    assert items[0]["entry_exists"] is True
    assert items[0]["path"] == str(root / "good")


def test_list_plugins_reports_missing_entries(tmp_path: Path) -> None:
    root = plugins.plugins_dir()
    directory = write_plugin(root, "demo")
    (directory / "plugin.py").unlink()

    [item] = plugins.list_plugins()

    assert item["entry_exists"] is False


def test_load_plugins_skips_disabled_and_missing_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = plugins.plugins_dir()
    write_plugin(root, "disabled", enabled=False)
    write_plugin(root, "missing")
    (root / "missing" / "plugin.py").unlink()
    monkeypatch.setattr(plugins, "check_plugin", lambda *_a, **_k: [])

    assert plugins.load_plugins() == []


def test_load_plugins_runs_an_allowed_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_plugin(plugins.plugins_dir(), "demo")
    monkeypatch.setattr(plugins, "check_plugin", lambda *_a, **_k: [])

    [loaded] = plugins.load_plugins()

    assert loaded["loaded"] is True
    assert "videoflow_plugin_demo" in __import__("sys").modules


def test_load_plugins_blocks_sandbox_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_plugin(plugins.plugins_dir(), "demo")
    monkeypatch.setattr(plugins, "check_plugin", lambda *_a, **_k: ["network"])

    [blocked] = plugins.load_plugins()

    assert blocked["loaded"] is False
    assert blocked["sandbox"] == ["network"]
    assert "sandbox" in str(blocked["error"])


def test_load_plugins_reports_import_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = write_plugin(plugins.plugins_dir(), "demo")
    (directory / "plugin.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    monkeypatch.setattr(plugins, "check_plugin", lambda *_a, **_k: [])

    [failed] = plugins.load_plugins()

    assert failed["loaded"] is False
    assert "boom" in str(failed["error"])


def test_load_plugins_reports_missing_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_plugin(plugins.plugins_dir(), "demo")
    monkeypatch.setattr(plugins, "check_plugin", lambda *_a, **_k: [])
    monkeypatch.setattr(plugins.importlib.util, "spec_from_file_location", lambda *_a: None)

    [failed] = plugins.load_plugins()

    assert failed["loaded"] is False
    assert "cannot load" in str(failed["error"])


def test_set_plugin_enabled_toggles_and_validates(tmp_path: Path) -> None:
    directory = write_plugin(plugins.plugins_dir(), "demo")

    updated = plugins.set_plugin_enabled("demo", False)

    assert updated["enabled"] is False
    payload = json.loads((directory / "plugin.json").read_text(encoding="utf-8"))
    assert payload["enabled"] is False

    with pytest.raises(ValueError, match="Unknown plugin"):
        plugins.set_plugin_enabled("missing", True)


def test_set_plugin_enabled_skips_corrupt_manifests(tmp_path: Path) -> None:
    root = plugins.plugins_dir()
    root.mkdir(parents=True)
    (root / "broken").mkdir()
    (root / "broken" / "plugin.json").write_text("{not json", encoding="utf-8")
    write_plugin(root, "good")

    updated = plugins.set_plugin_enabled("good", False)

    assert updated["id"] == "good"


def test_plugin_summary_counts_state(tmp_path: Path) -> None:
    root = plugins.plugins_dir()
    write_plugin(root, "one", enabled=True)
    write_plugin(root, "two", enabled=False)

    summary = plugins.plugin_summary()

    assert summary["ok"] is True
    assert summary["enabled"] == 1
    assert summary["loaded"] == 2
    assert len(summary["plugins"]) == 2
