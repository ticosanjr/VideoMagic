"""Folder browser API and the Windows native picker."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from videoflow.api import routes_system


def test_browse_folders_lists_child_directories(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")

    listing = routes_system._browse_folders(str(tmp_path))

    assert listing["path"] == str(tmp_path.resolve())
    names = [item["name"] for item in listing["directories"]]
    assert names == ["alpha", "beta"]
    assert listing["parent"] == str(tmp_path.resolve().parent)
    assert str(tmp_path.resolve()) in listing["roots"] or listing["roots"]


def test_browse_folders_falls_back_to_the_nearest_existing_parent(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing" / "nested"

    listing = routes_system._browse_folders(str(missing))

    assert listing["path"] == str(tmp_path.resolve())


def test_windows_picker_uses_powershell_winforms(monkeypatch) -> None:
    monkeypatch.setattr(routes_system, "_is_windows", lambda: True)
    monkeypatch.setattr(
        routes_system.shutil,
        "which",
        lambda name: "/usr/bin/powershell" if name in {"powershell", "pwsh"} else None,
    )
    captured: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs.get("env")
        return SimpleNamespace(returncode=0, stdout=r"C:\Work\Video", stderr="")

    monkeypatch.setattr(routes_system.subprocess, "run", fake_run)

    selected = routes_system._choose_folder(r"C:\Work")

    assert selected == r"C:\Work\Video"
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert "-STA" in argv
    assert any("System.Windows.Forms" in str(item) for item in argv)
    assert captured["env"]["VF_INITIAL_DIR"] == r"C:\Work"


def test_windows_picker_returns_empty_when_cancelled(monkeypatch) -> None:
    monkeypatch.setattr(routes_system, "_is_windows", lambda: True)
    monkeypatch.setattr(
        routes_system.shutil,
        "which",
        lambda name: "/usr/bin/powershell" if name in {"powershell", "pwsh"} else None,
    )
    monkeypatch.setattr(
        routes_system.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    assert routes_system._choose_folder("") == ""
