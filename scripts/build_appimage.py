"""Build a portable Linux AppImage around the PyInstaller onefile binary.

The AppImage is a single self-mounting file. It keeps the same bundled Python,
UI, presets, and static FFmpeg as the plain binary. Data is written next to the
AppImage (``videoflow-data``) unless ``VIDEOWFLOW_HOME`` says otherwise.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPIMAGETOOL_URL = (
    "https://github.com/AppImage/appimagetool/releases/download/continuous/"
    "appimagetool-x86_64.AppImage"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Linux AppImage.")
    parser.add_argument("--binary", type=Path, default=ROOT / "dist" / "videoflow")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--work", type=Path, default=ROOT / "build" / "appimage")
    args = parser.parse_args()
    if not args.binary.is_file():
        print(f"binary not found: {args.binary}. Build the onefile first.")
        return 1

    appdir = args.work / "AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr" / "bin").mkdir(parents=True)
    (appdir / "usr" / "share" / "applications").mkdir(parents=True)
    (appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True)

    target = appdir / "usr" / "bin" / "videoflow"
    shutil.copy2(args.binary, target)
    target.chmod(0o755)

    apprun = appdir / "AppRun"
    apprun.write_text(
        '#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/bin/videoflow" "$@"\n',
        encoding="utf-8",
    )
    apprun.chmod(apprun.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    desktop = """[Desktop Entry]
Type=Application
Name=VideoFlow
Comment=Portable non-destructive video pre-edit pipeline
Exec=videoflow
Icon=videoflow
Terminal=true
Categories=AudioVideo;Video;
"""
    (appdir / "videoflow.desktop").write_text(desktop, encoding="utf-8")
    (appdir / "usr" / "share" / "applications" / "videoflow.desktop").write_text(
        desktop, encoding="utf-8"
    )
    icon = appdir / "videoflow.png"
    _make_icon(icon)
    shutil.copy2(
        icon, appdir / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "videoflow.png"
    )

    tool = _appimagetool(ROOT / "build" / "tools")
    args.out.mkdir(parents=True, exist_ok=True)
    output = args.out / "VideoFlow-x86_64.AppImage"
    environment = dict(os.environ)
    environment["ARCH"] = "x86_64"
    command = [str(tool), "--appimage-extract-and-run", str(appdir), str(output)]
    completed = subprocess.run(command, env=environment, check=False)
    if completed.returncode != 0:
        return completed.returncode
    output.chmod(0o755)
    print(f"built {output} ({output.stat().st_size / 1_000_000:.1f} MB)")
    return 0


def _appimagetool(tools: Path) -> Path:
    target = tools / "appimagetool-x86_64.AppImage"
    if target.is_file():
        return target
    tools.mkdir(parents=True, exist_ok=True)
    print(f"downloading {APPIMAGETOOL_URL}")
    with (
        urllib.request.urlopen(APPIMAGETOOL_URL, timeout=120) as response,
        target.open("wb") as handle,
    ):
        shutil.copyfileobj(response, handle)
    target.chmod(0o755)
    return target


def _make_icon(path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is not None:
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x0ea5e9:s=256x256",
            "-frames:v",
            "1",
            "-vf",
            "drawtext=text='VF':fontcolor=white:fontsize=96:x=(w-text_w)/2:y=(h-text_h)/2",
            str(path),
        ]
        if subprocess.run(command, check=False).returncode == 0:
            return
        fallback = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x0ea5e9:s=256x256",
            "-frames:v",
            "1",
            str(path),
        ]
        if subprocess.run(fallback, check=False).returncode == 0:
            return
    raise SystemExit("could not generate an icon; install FFmpeg with drawtext or add one")


if __name__ == "__main__":
    sys.exit(main())
