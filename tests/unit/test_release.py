from pathlib import Path

import pytest
from scripts.release import _prune_old_releases


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
