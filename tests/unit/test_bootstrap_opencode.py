"""OpenCode workspace bootstrap: files, config merge, styles, and CLI/API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow import cli
from videoflow.api.app import create_app
from videoflow.application import opencode_config
from videoflow.application.settings import load_settings
from videoflow.bootstrap import BootstrapRequest, bootstrap_opencode_workspace, templates_dir


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path / "global-opencode"))


def _bootstrap(tmp_path: Path, **updates):
    values = {"mcp_profile": "full", "register_root": True, **updates}
    request = BootstrapRequest(
        target_dir=str(tmp_path / "workspace"),
        **values,
    )
    return bootstrap_opencode_workspace(request)


def test_templates_are_packaged() -> None:
    assert (templates_dir() / "AGENTS.md").is_file()
    assert len(list((templates_dir() / "skills").glob("*.md"))) == 3
    assert len(list((templates_dir() / "commands").glob("*.md"))) == 7


def test_bootstrap_creates_workspace_and_syncs_styles(tmp_path: Path) -> None:
    result = _bootstrap(tmp_path)
    target = tmp_path / "workspace"

    assert result.status == "ok"
    assert result.registered_root is True
    assert result.mcp_servers == ["core"]
    assert result.launch_command == f'cd "{target}" && opencode'
    assert result.copied_styles
    assert len(result.copied_workflows) == 5

    config = json.loads((target / "opencode.json").read_text(encoding="utf-8"))
    assert set(config["mcp"]["servers"]) == {"core"}
    core = config["mcp"]["servers"]["core"]
    assert core["environment"]["VF_WORKSPACE_ROOT"] == str(target / "projects")
    assert "VIDEOWFLOW_HOME" not in core["environment"]
    assert config["mcp"]["timeout"]["startup"] >= 100000
    assert "VF_GPU_WORKER_TOKEN" not in core["environment"]
    assert "VF_GPU_WORKER_URL" not in core["environment"]
    assert "VF_COMPUTE_MODE" not in core["environment"]
    assert "videoflow-mcp" in core["command"]

    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count("<!-- videoflow:opencode:start -->") == 1
    assert "canal-paula-reels" in agents
    assert "antes de decupar" in agents.lower()
    assert str(target) in agents

    assert len(list((target / ".opencode" / "skills").glob("*.md"))) == 3
    assert len(list((target / ".opencode" / "commands").glob("*.md"))) == 7
    assert len(list((target / ".opencode" / "workflows").glob("*.md"))) == 5
    assert (target / "presets" / "canal-paula-reels.md").is_file()
    assert (target / "presets" / ".videoflow-styles.json").is_file()
    assert (target / "references").is_dir()
    assert (target / "projects").is_dir()

    settings = load_settings()
    assert str(target.resolve()) in settings.paths.allowed_roots


def test_bootstrap_is_idempotent_and_preserves_user_agents_text(tmp_path: Path) -> None:
    target = tmp_path / "workspace"
    _bootstrap(tmp_path)
    agents = target / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\n## Minhas notas\n\nNão apagar.\n",
        encoding="utf-8",
    )

    second = _bootstrap(tmp_path)

    assert second.status == "ok"
    text = agents.read_text(encoding="utf-8")
    assert text.count("<!-- videoflow:opencode:start -->") == 1
    assert "Minhas notas" in text
    assert "Não apagar." in text


def test_bootstrap_merges_global_config_and_keeps_other_servers(tmp_path: Path) -> None:
    global_file = tmp_path / "global-opencode" / "opencode.json"
    global_file.parent.mkdir(parents=True)
    global_file.write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "model": "deepseek/deepseek-chat",
                "mcp": {"servers": {"other": {"type": "local", "command": ["other"]}}},
            }
        ),
        encoding="utf-8",
    )

    result = _bootstrap(
        tmp_path,
        mcp_profile="core",
        register_global_opencode=True,
    )

    assert result.status == "ok"
    merged = json.loads(global_file.read_text(encoding="utf-8"))
    assert merged["model"] == "deepseek/deepseek-chat"
    assert "other" in merged["mcp"]["servers"]
    assert "core" in merged["mcp"]["servers"]
    assert list(global_file.parent.glob("opencode.json.bak-*"))


def test_bootstrap_refuses_unparseable_global_config_without_overwrite(tmp_path: Path) -> None:
    global_file = tmp_path / "global-opencode" / "opencode.json"
    global_file.parent.mkdir(parents=True)
    global_file.write_text("{ // jsonc\n", encoding="utf-8")

    result = _bootstrap(
        tmp_path,
        mcp_profile="core",
        register_global_opencode=True,
        overwrite=False,
    )

    assert result.status == "warning"
    assert any("not plain JSON" in item for item in result.warnings)
    assert global_file.read_text(encoding="utf-8") == "{ // jsonc\n"


def test_bootstrap_sample_project_is_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "videoflow.bootstrap.opencode_workspace._sample_project",
        lambda target: {"ok": True, "project_id": "sample"},
    )
    result = _bootstrap(tmp_path, include_sample_project=True)
    assert result.sample_project["project_id"] == "sample"


def test_bootstrap_is_local_only_by_default(tmp_path: Path) -> None:
    global_file = tmp_path / "global-opencode" / "opencode.json"
    result = _bootstrap(tmp_path, mcp_profile="core")
    assert result.status == "ok"
    assert global_file.exists() is False
    local = json.loads((tmp_path / "workspace" / "opencode.json").read_text(encoding="utf-8"))
    assert "core" in local["mcp"]["servers"]


def test_cleanup_global_removes_only_videoflow_servers(tmp_path: Path) -> None:
    from videoflow.bootstrap import remove_global_videoflow_servers

    global_file = tmp_path / "global-opencode" / "opencode.json"
    global_file.parent.mkdir(parents=True)
    global_file.write_text(
        json.dumps(
            {
                "model": "x",
                "mcp": {
                    "servers": {
                        "core": {
                            "type": "local",
                            "command": ["/tmp/.mount_old/usr/bin/videoflow", "mcp"],
                        },
                        "fetch": {
                            "type": "local",
                            "command": ["videoflow-mcp-fetch"],
                        },
                        "other": {"type": "local", "command": ["other"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    result = remove_global_videoflow_servers()
    assert result["ok"] is True
    assert result["removed"] == ["core", "fetch"]
    merged = json.loads(global_file.read_text(encoding="utf-8"))
    assert merged["model"] == "x"
    assert set(merged["mcp"]["servers"]) == {"other"}
    assert result["backup"]


def test_opencode_config_packaged_and_merge() -> None:
    generated = opencode_config.build_config(
        "core",
        workspace_root="/work/projects",
        prompts=False,
    )
    assert generated["$schema"] == "https://opencode.ai/config.json"
    assert generated["mcp"]["servers"]["core"]["environment"]["VF_MCP_PROMPTS"] == "0"

    merged = opencode_config.merge_config(
        {"model": "x", "mcp": {"servers": {"other": {"type": "local"}}}},
        generated,
    )
    assert merged["model"] == "x"
    assert "other" in merged["mcp"]["servers"]
    assert "core" in merged["mcp"]["servers"]


def test_opencode_config_packaged_commands(monkeypatch) -> None:
    monkeypatch.setattr(opencode_config, "is_packaged", lambda: True)
    core = opencode_config.server_block("core", workspace_root="/w")
    assert core["command"][-1] == "mcp"
    assert core["timeout"]["startup"] == 120000
    with pytest.raises(ValueError):
        opencode_config.server_block("fetch", workspace_root="/w")


def test_stable_mcp_launcher_uses_appimage(tmp_path: Path, monkeypatch) -> None:
    appimage = tmp_path / "VideoFlow.AppImage"
    appimage.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("APPIMAGE", str(appimage))
    launcher = tmp_path / "launcher" / "videoflow"
    monkeypatch.setattr(opencode_config, "mcp_launcher_path", lambda: launcher)
    assert opencode_config.ensure_mcp_launcher() == str(launcher)
    assert launcher.is_file()
    assert str(appimage) in launcher.read_text(encoding="utf-8")


def test_bootstrap_api_route(tmp_path: Path) -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/system/bootstrap/opencode",
        json={
            "target_dir": str(tmp_path / "api-workspace"),
            "mcp_profile": "core",
            "register_root": True,
            "overwrite": False,
        },
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["mcp_servers"] == ["core"]
    assert (tmp_path / "api-workspace" / "opencode.json").is_file()


def test_bootstrap_cli(tmp_path, capsys) -> None:
    target = tmp_path / "cli-workspace"
    assert (
        cli.main(
            [
                "init-opencode",
                str(target),
                "--profile",
                "core",
                "--no-register-root",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert (target / "opencode.json").is_file()


def test_bootstrap_appends_managed_block_to_existing_agents(tmp_path: Path) -> None:
    target = tmp_path / "workspace"
    target.mkdir()
    (target / "AGENTS.md").write_text("# Instruções antigas\n\nManter.\n", encoding="utf-8")

    result = _bootstrap(tmp_path)

    text = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert "Instruções antigas" in text
    assert text.count("<!-- videoflow:opencode:start -->") == 1
    assert any("(appended)" in item for item in result.created_files)


def test_bootstrap_rejects_file_and_root_targets(tmp_path: Path) -> None:
    file_target = tmp_path / "file.txt"
    file_target.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        bootstrap_opencode_workspace(BootstrapRequest(target_dir=str(file_target)))
    with pytest.raises(ValueError):
        bootstrap_opencode_workspace(BootstrapRequest(target_dir="/"))


def test_bootstrap_backup_helpers_and_invalid_overwrite(tmp_path: Path) -> None:
    from videoflow.bootstrap.opencode_workspace import _backup, _merge_json_file

    assert _backup(tmp_path / "missing.json") is None
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    assert _backup(source) is not None

    path = tmp_path / "bad.json"
    path.write_text("{ // comments\n", encoding="utf-8")
    warnings: list[str] = []
    _merge_json_file(path, {"mcp": {"servers": {}}}, overwrite=True, warnings=warnings)
    assert warnings
    assert json.loads(path.read_text(encoding="utf-8"))["mcp"] == {"servers": {}}
    assert list(tmp_path.glob("bad.json.bak-*"))


def test_sample_project_without_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "videoflow.bootstrap.opencode_workspace.find_binary",
        lambda *args: None,
    )
    from videoflow.bootstrap.opencode_workspace import _sample_project

    result = _sample_project(tmp_path)
    assert result["ok"] is False
    assert "ffmpeg" in result["warning"]


def test_opencode_config_errors_and_platform_paths(tmp_path, monkeypatch) -> None:
    with pytest.raises(ValueError):
        opencode_config.server_block("unknown", workspace_root="/w")
    with pytest.raises(ValueError):
        opencode_config.build_config("unknown", workspace_root="/w")

    merged = opencode_config.merge_config(
        {"mcp": "bad", "servers": []},
        {"mcp": {"servers": {"core": {"type": "local"}}}},
    )
    assert merged["mcp"]["servers"]["core"]["type"] == "local"

    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path / "opencode"))
    assert opencode_config.global_config_path() == tmp_path / "opencode" / "opencode.json"

    monkeypatch.delenv("OPENCODE_CONFIG_DIR")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert opencode_config.global_config_path() == tmp_path / "xdg" / "opencode" / "opencode.json"

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(opencode_config.sys, "platform", "win32")
    assert opencode_config.global_config_path() == (
        tmp_path / "appdata" / "opencode" / "opencode.json"
    )


def test_bootstrap_api_and_cli_errors(tmp_path: Path, capsys) -> None:
    client = TestClient(create_app())
    api = client.post(
        "/api/v1/system/bootstrap/opencode",
        json={"target_dir": "/", "mcp_profile": "core"},
    )
    assert api.status_code == 400
    assert api.json()["detail"]["code"] == "bootstrap_failed"

    assert cli.main(["init-opencode", "/", "--profile", "core", "--no-register-root"]) == 1
    assert "bootstrap_failed" in capsys.readouterr().err


def test_mcp_health_and_cleanup_routes(tmp_path: Path) -> None:
    global_file = tmp_path / "global-opencode" / "opencode.json"
    global_file.parent.mkdir(parents=True)
    global_file.write_text(
        json.dumps(
            {
                "mcp": {
                    "servers": {
                        "core": {
                            "type": "local",
                            "command": ["/tmp/.mount_old/usr/bin/videoflow", "mcp"],
                        },
                        "other": {"type": "local", "command": ["other"]},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app())
    health = client.get("/api/v1/system/opencode/mcp-health")
    assert health.status_code == 200, health.text
    payload = health.json()
    assert "core" in payload["global_videoflow_servers"]
    assert any("missing executable" in item for item in payload["warnings"])

    cleaned = client.post("/api/v1/system/opencode/cleanup-global")
    assert cleaned.status_code == 200, cleaned.text
    assert cleaned.json()["removed"] == ["core"]
    merged = json.loads(global_file.read_text(encoding="utf-8"))
    assert set(merged["mcp"]["servers"]) == {"other"}
