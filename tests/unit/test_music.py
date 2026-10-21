from pathlib import Path

import pytest

from videoflow.application.music import list_music, music_filter, save_music
from videoflow.domain.errors import FilesystemError


def test_music_filter_ducking_and_fades() -> None:
    filter_complex = music_filter(10.0, volume=0.2, ducking=True, fade_in_ms=500, fade_out_ms=1000)
    assert "volume=0.2" in filter_complex
    assert "atrim=0:10.000" in filter_complex
    assert "sidechaincompress" in filter_complex
    assert "afade=t=in:st=0:d=0.500" in filter_complex
    assert "afade=t=out:st=9.000:d=1.000" in filter_complex
    assert music_filter(10.0, ducking=False).count("amix") == 1


def test_music_store_roundtrip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    asset = save_music("Track.MP3", b"ID3fake")
    assert Path(asset["file"]).is_file()
    assert asset["name"].endswith(".mp3")
    assert len(list_music()) == 1


def test_music_store_rejects_invalid_suffix(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    with pytest.raises(FilesystemError):
        save_music("track.txt", b"nope")
