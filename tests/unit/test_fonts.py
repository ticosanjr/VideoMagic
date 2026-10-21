from pathlib import Path

import pytest

from videoflow.application.fonts import font_family, list_fonts, save_font
from videoflow.domain.errors import FilesystemError

SYSTEM_FONT = Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf")


def test_font_parser_reads_a_system_family() -> None:
    if not SYSTEM_FONT.is_file():
        pytest.skip("system test font is not installed")
    family = font_family(SYSTEM_FONT.read_bytes())
    assert family


def test_font_upload_store_roundtrip(monkeypatch, tmp_path: Path) -> None:
    if not SYSTEM_FONT.is_file():
        pytest.skip("system test font is not installed")
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    asset = save_font("Custom.ttf", SYSTEM_FONT.read_bytes())
    assert Path(asset["file"]).is_file()
    assert asset["family"]
    fonts = list_fonts()
    assert len(fonts) == 1
    assert fonts[0]["family"] == asset["family"]


def test_font_upload_rejects_invalid_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    with pytest.raises(FilesystemError):
        save_font("bad.ttf", b"not a font")
    with pytest.raises(FilesystemError):
        save_font("bad.woff", b"not a font")
