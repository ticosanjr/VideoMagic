from __future__ import annotations

from pathlib import Path

from vf_shared.contracts.workspace import project_dir, workspace_root


def test_workspace_root_accepts_a_projects_directory(tmp_path: Path, monkeypatch) -> None:
    projects = tmp_path / "projects"
    monkeypatch.setenv("VF_WORKSPACE_ROOT", str(projects))
    assert workspace_root() == projects
    assert project_dir("abc") == projects / "abc"


def test_workspace_root_appends_projects_only_once(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    monkeypatch.setenv("VF_WORKSPACE_ROOT", str(root))
    assert project_dir("abc") == root / "projects" / "abc"
