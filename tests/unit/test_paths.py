from pathlib import Path

import pytest

from videoflow.domain.errors import PathJailError
from videoflow.domain.paths import resolve_allowed


def test_path_inside_a_root_is_returned(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    candidate = media / "take.mp4"
    assert resolve_allowed(candidate, [media]) == candidate.resolve()


def test_the_root_itself_is_allowed(tmp_path: Path) -> None:
    assert resolve_allowed(tmp_path, [tmp_path]) == tmp_path.resolve()


def test_path_outside_every_root_is_rejected(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "other" / "take.mp4"
    with pytest.raises(PathJailError):
        resolve_allowed(outside, [allowed])


def test_no_roots_rejects_everything(tmp_path: Path) -> None:
    with pytest.raises(PathJailError):
        resolve_allowed(tmp_path / "x.mp4", [])


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "hidden.mp4").write_bytes(b"x")
    link = allowed / "link"
    link.symlink_to(secret_dir, target_is_directory=True)
    with pytest.raises(PathJailError):
        resolve_allowed(link / "hidden.mp4", [allowed])


def test_parent_traversal_is_rejected(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with pytest.raises(PathJailError):
        resolve_allowed(allowed / ".." / "escape.mp4", [allowed])
