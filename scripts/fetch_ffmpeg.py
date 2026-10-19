"""Fetch static FFmpeg/FFprobe binaries for a portable build.

Linux and Windows artifacts come from the BtbN GPL builds. They are self-contained
so the executable does not depend on the host's FFmpeg installation. Review the
FFmpeg license before distributing a bundled build.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

URLS = {
    "linux": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-linux64-gpl.tar.xz",
    "windows": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip",
}

ROOT = Path(__file__).resolve().parents[1]


def current_platform() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    raise SystemExit("Only Linux and Windows portable builds are supported.")


def fetch(target: str, destination: Path) -> None:
    url = URLS[target]
    destination.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}")
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / ("ffmpeg.zip" if target == "windows" else "ffmpeg.tar.xz")
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)
        print(f"downloaded {archive.stat().st_size / 1_000_000:.1f} MB")
        extract_dir = Path(temporary) / "extract"
        extract_dir.mkdir()
        if target == "windows":
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(extract_dir)
            names = ("ffmpeg.exe", "ffprobe.exe")
        else:
            with tarfile.open(archive, "r:xz") as bundle:
                bundle.extractall(extract_dir)
            names = ("ffmpeg", "ffprobe")
        for name in names:
            matches = [path for path in extract_dir.rglob(name) if path.is_file()]
            if not matches:
                raise SystemExit(f"{name} was not found in the downloaded archive")
            source = next((path for path in matches if path.parent.name == "bin"), matches[0])
            target_path = destination / name
            shutil.copy2(source, target_path)
            if os.name != "nt":
                target_path.chmod(0o755)
            print(f"installed {target_path} ({target_path.stat().st_size / 1_000_000:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download static FFmpeg binaries.")
    parser.add_argument("--platform", choices=("auto", "linux", "windows"), default="auto")
    parser.add_argument("--dest", type=Path, default=ROOT / "vendor")
    args = parser.parse_args()
    target = current_platform() if args.platform == "auto" else args.platform
    if target == "windows" and os.name != "nt":
        print("warning: downloading Windows binaries on a non-Windows host", file=sys.stderr)
    fetch(target, args.dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
