from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.domain.errors import FilesystemError
from videoflow.domains.media.asset_store import list_files, save_file


def test_save_file_writes_hashed_name(tmp_path: Path) -> None:
    result = save_file(
        "My Song.mp3",
        b"abc",
        directory=tmp_path,
        suffixes={".mp3"},
        max_bytes=10,
        label="music",
        default_stem="music",
    )
    assert result["sha256"]
    assert (tmp_path / result["name"]).read_bytes() == b"abc"
    assert list_files(tmp_path, {".mp3"})[0]["name"] == result["name"]


def test_save_file_rejects_empty_large_and_bad_suffix(tmp_path: Path) -> None:
    with pytest.raises(FilesystemError, match="empty"):
        save_file(
            "a.mp3",
            b"",
            directory=tmp_path,
            suffixes={".mp3"},
            max_bytes=10,
            label="music",
            default_stem="music",
        )
    with pytest.raises(FilesystemError, match="at most"):
        save_file(
            "a.mp3",
            b"x" * 11,
            directory=tmp_path,
            suffixes={".mp3"},
            max_bytes=10,
            label="music",
            default_stem="music",
        )
    with pytest.raises(FilesystemError, match="Use"):
        save_file(
            "a.wav",
            b"x",
            directory=tmp_path,
            suffixes={".mp3"},
            max_bytes=10,
            label="music",
            default_stem="music",
        )
