"""Font store: SFNT name parsing, uploads, listing, and deletion."""

from __future__ import annotations

import struct

import pytest

from videoflow.application import fonts
from videoflow.domain.errors import FilesystemError


def sfnt(family: str = "VideoFlow Sans", *, include_name: bool = True) -> bytes:
    text = family.encode("utf-16-be")
    record = struct.pack(">HHHHHH", 3, 1, 0x0409, 16, len(text), 0)
    table = struct.pack(">HH", 0, 1) + struct.pack(">H", 6 + len(record)) + record + text
    header = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 1, 0, 0, 0)
    if not include_name:
        return header + struct.pack(">4sIII", b"head", 0, 28, 4) + b"\x00\x00\x00\x00"
    offset = 12 + 16
    directory = struct.pack(">4sIII", b"name", 0, offset, len(table))
    return header + directory + table


def test_font_family_reads_the_typographic_name() -> None:
    assert fonts.font_family(sfnt()) == "VideoFlow Sans"


def test_font_family_rejects_invalid_files() -> None:
    with pytest.raises(FilesystemError, match="not a TrueType"):
        fonts.font_family(b"nope")
    with pytest.raises(FilesystemError, match="no readable name table"):
        fonts.font_family(sfnt(include_name=False))

    text = b""
    record = struct.pack(">HHHHHH", 3, 1, 0x0409, 16, len(text), 0)
    table = struct.pack(">HH", 0, 1) + struct.pack(">H", 6 + len(record)) + record + text
    header = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 1, 0, 0, 0)
    directory = struct.pack(">4sIII", b"name", 0, 28, len(table))
    with pytest.raises(FilesystemError, match="no family name"):
        fonts.font_family(header + directory + table)

    truncated = bytearray(sfnt())
    truncated[4:6] = struct.pack(">H", 5000)
    assert fonts.font_family(bytes(truncated)) == "VideoFlow Sans"


def test_save_font_writes_a_hashed_name() -> None:
    payload = fonts.save_font("../../My Font.ttf", sfnt())

    target = fonts.fonts_dir() / str(payload["name"])
    assert target.is_file()
    assert target.name.startswith("My-Font-")
    assert target.suffix == ".ttf"
    assert payload["family"] == "VideoFlow Sans"
    assert len(str(payload["sha256"])) == 64
    assert payload["size_bytes"] == len(sfnt())


def test_save_font_validates_content_and_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(FilesystemError, match="empty"):
        fonts.save_font("font.ttf", b"")

    monkeypatch.setattr(fonts, "MAX_FONT_BYTES", 4)
    with pytest.raises(FilesystemError, match="at most"):
        fonts.save_font("font.ttf", b"12345")

    with pytest.raises(FilesystemError, match="Only .ttf and .otf"):
        fonts.save_font("font.woff", b"1234")


def test_list_fonts_skips_other_files_and_falls_back_to_stems() -> None:
    good = fonts.save_font("Good.ttf", sfnt())
    directory = fonts.fonts_dir()
    (directory / "notes.txt").write_text("nope", encoding="utf-8")
    (directory / "broken.ttf").write_bytes(b"not a font")

    listed = fonts.list_fonts()

    assert [item["name"] for item in listed] == [good["name"], "broken.ttf"]
    assert listed[0]["family"] == "VideoFlow Sans"
    assert listed[1]["family"] == "broken"


def test_delete_fonts_removes_known_assets_only() -> None:
    payload = fonts.save_font("Good.ttf", sfnt())

    fonts.delete_fonts(str(payload["name"]))

    assert not (fonts.fonts_dir() / str(payload["name"])).exists()
    with pytest.raises(FilesystemError, match="Unknown fonts asset"):
        fonts.delete_fonts("missing.ttf")
