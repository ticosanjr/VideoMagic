import os
import subprocess
import sys
from pathlib import Path

from scripts.build_appimage import build_appdir


def fake_binary(tmp_path: Path) -> Path:
    binary = tmp_path / "videoflow"
    binary.write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
    binary.chmod(0o755)
    return binary


def fake_icon(tmp_path: Path) -> Path:
    icon = tmp_path / "icon.png"
    icon.write_bytes(b"\x89PNG\r\n\x1a\n")
    return icon


def test_appdir_contains_launcher_desktop_and_icon(tmp_path: Path) -> None:
    appdir = build_appdir(
        fake_binary(tmp_path),
        tmp_path / "work",
        icon=fake_icon(tmp_path),
    )
    apprun = appdir / "AppRun"
    text = apprun.read_text(encoding="utf-8")
    assert "serve --open" in text
    assert os.access(apprun, os.X_OK)
    assert (appdir / "usr" / "bin" / "videoflow").is_file()
    assert (appdir / "videoflow.desktop").is_file()
    assert (appdir / "videoflow.png").is_file()
    assert (appdir / "usr/share/icons/hicolor/256x256/apps/videoflow.png").is_file()
    assert "Exec=videoflow" in (appdir / "videoflow.desktop").read_text(encoding="utf-8")


def test_build_appimage_appdir_only_mode(tmp_path: Path) -> None:
    binary = fake_binary(tmp_path)
    icon = fake_icon(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/build_appimage.py",
            "--binary",
            str(binary),
            "--work",
            str(tmp_path / "work"),
            "--icon",
            str(icon),
            "--appdir-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "appdir ready" in completed.stdout
    assert (tmp_path / "work" / "AppDir" / "AppRun").is_file()
