from __future__ import annotations

from pathlib import Path

from videoflow.application import remote_fonts


def test_remote_font_paths_returns_only_font_files(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "Inter.ttf").write_bytes(b"font")
    (tmp_path / "Mono.OTF").write_bytes(b"font")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(remote_fonts, "fonts_dir", lambda: tmp_path)

    paths = remote_fonts.remote_font_paths()

    assert [Path(item).name for item in paths] == ["Inter.ttf", "Mono.OTF"]


def test_remote_font_paths_handles_a_missing_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(remote_fonts, "fonts_dir", lambda: tmp_path / "missing")

    assert remote_fonts.remote_font_paths() == []
