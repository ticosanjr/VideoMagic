"""Plugin sandbox policy and exporter/provider registration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.contract.test_exporters import sample_state
from videoflow import plugin_api
from videoflow.application.export_service import export_timeline
from videoflow.application.plugins import load_plugins
from videoflow.application.providers import first_provider
from videoflow.domain.errors import ExportError


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    plugin_api.reset()
    yield
    plugin_api.reset()


def write_plugin(
    home: Path,
    plugin_id: str,
    *,
    source: str,
    permissions: list[str],
    provides: list[str],
) -> Path:
    directory = home / "plugins" / plugin_id
    directory.mkdir(parents=True)
    (directory / "plugin.json").write_text(
        json.dumps(
            {
                "id": plugin_id,
                "name": plugin_id,
                "entry": "plugin.py",
                "enabled": True,
                "permissions": permissions,
                "provides": provides,
            }
        ),
        encoding="utf-8",
    )
    (directory / "plugin.py").write_text(source, encoding="utf-8")
    return directory


def test_plugin_registers_exporter_and_provider(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_plugin(
        home,
        "shiny",
        permissions=[],
        provides=["exporter", "provider"],
        source=(
            "from pathlib import Path\n"
            "from videoflow.plugin_api import register_exporter, register_provider\n"
            "def write(state, directory):\n"
            "    target = Path(directory) / 'timeline.plugin.json'\n"
            "    target.write_text('{}', encoding='utf-8')\n"
            "    return target\n"
            "register_exporter('shiny', write)\n"
            "register_provider('llm', {'name': 'plugin-llm', 'model': 'local'})\n"
        ),
    )

    loaded = load_plugins()

    assert loaded[0]["loaded"] is True, loaded[0]
    assert first_provider("llm")["name"] == "plugin-llm"
    state = sample_state(tmp_path)
    directory = tmp_path / "exports"
    directory.mkdir()
    artifacts = export_timeline(state, directory, targets=["shiny"])
    assert artifacts["shiny"].name == "timeline.plugin.json"


def test_sandbox_blocks_shell_imports_without_permission(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_plugin(
        home,
        "sneaky",
        permissions=[],
        provides=["step"],
        source="import subprocess\nsubprocess.run(['true'])\n",
    )

    loaded = load_plugins()

    assert loaded[0]["loaded"] is False
    assert loaded[0]["sandbox"]


def test_sandbox_allows_shell_imports_with_permission(tmp_path: Path) -> None:
    home = tmp_path / "home"
    write_plugin(
        home,
        "tool",
        permissions=["shell"],
        provides=["step"],
        source="import subprocess\nsubprocess.run(['true'])\n",
    )

    loaded = load_plugins()

    assert loaded[0]["loaded"] is True, loaded[0]


def test_unknown_export_target_still_fails(tmp_path: Path) -> None:
    state = sample_state(tmp_path)
    directory = tmp_path / "exports"
    directory.mkdir()
    with pytest.raises(ExportError):
        export_timeline(state, directory, targets=["missing"])
