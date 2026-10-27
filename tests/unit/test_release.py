from pathlib import Path

import pytest
from scripts.release import _prune_old_releases, _release_notes


def test_prune_old_releases_keeps_newest_three(tmp_path: Path) -> None:
    for version in ("v0.9.0", "v0.10.0", "v0.10.1", "v0.11.0", "v0.2.0"):
        (tmp_path / version).mkdir()
    (tmp_path / "README.md").write_text("keep", encoding="utf-8")

    removed = _prune_old_releases(tmp_path)

    assert {path.name for path in removed} == {"v0.2.0", "v0.9.0"}
    assert {path.name for path in tmp_path.iterdir()} == {
        "README.md",
        "v0.10.0",
        "v0.10.1",
        "v0.11.0",
    }
    with pytest.raises(ValueError, match="keep must be at least 1"):
        _prune_old_releases(tmp_path, keep=0)


def test_release_notes_list_only_staged_linux_artifacts() -> None:
    notes = _release_notes(
        "9.9.9",
        [
            {"name": "videoflow-9.9.9-linux-x86_64", "sha256": "a" * 64},
            {"name": "VideoFlow-9.9.9-x86_64.AppImage", "sha256": "b" * 64},
            {"name": "sbom.json", "sha256": "c" * 64},
        ],
    )

    assert "Linux plain binary" in notes
    assert "./videoflow-9.9.9-linux-x86_64 doctor" in notes
    assert "chmod +x VideoFlow-9.9.9-x86_64.AppImage" in notes
    assert "Windows" not in notes


def test_release_notes_describe_windows_only_when_staged() -> None:
    notes = _release_notes(
        "9.9.9",
        [{"name": "videoflow-9.9.9-windows-x86_64.exe", "sha256": "d" * 64}],
    )

    assert "Windows:" in notes
    assert ".\\videoflow-9.9.9-windows-x86_64.exe doctor" in notes
    assert "smoke-tested under Wine" in notes
    assert "Linux plain binary" not in notes
