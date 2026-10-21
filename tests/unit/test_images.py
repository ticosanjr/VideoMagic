from pathlib import Path

import pytest

from videoflow.application.images import list_images, save_image
from videoflow.domain.errors import FilesystemError

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_image_store_roundtrip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    asset = save_image("Logo.PNG", PNG)
    assert Path(asset["file"]).is_file()
    assert asset["name"].endswith(".png")
    assert len(list_images()) == 1


def test_image_store_rejects_invalid_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    with pytest.raises(FilesystemError):
        save_image("bad.png", b"not an image")
    with pytest.raises(FilesystemError):
        save_image("bad.gif", PNG)
