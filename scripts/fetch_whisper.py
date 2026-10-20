"""Fetch whisper.cpp and a tiny GGML model for the portable build.

Linux builds ``whisper-cli`` from the pinned upstream source. Windows downloads
the official x64 release. Both paths also fetch ``ggml-tiny.bin`` (~75 MB).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v1.7.6"
SOURCE_URL = f"https://github.com/ggml-org/whisper.cpp/archive/refs/tags/{VERSION}.tar.gz"
WINDOWS_URL = (
    "https://github.com/ggml-org/whisper.cpp/releases/download/"
    f"{VERSION}/whisper-bin-x64.zip"
)
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin"


def fetch(platform: str, dest: Path, *, refresh: bool = False) -> Path:
    target = dest / "whisper"
    target.mkdir(parents=True, exist_ok=True)
    _model(target, refresh=refresh)
    if platform == "windows":
        _windows(target, refresh=refresh)
    else:
        _linux(target, refresh=refresh)
    total = sum(path.stat().st_size for path in target.iterdir() if path.is_file())
    print(f"whisper ready: {target} ({total / 1_000_000:.1f} MB)")
    return target


def _model(target: Path, *, refresh: bool) -> None:
    path = target / "ggml-tiny.bin"
    if path.is_file() and not refresh:
        print(f"reusing {path}")
        return
    _download(MODEL_URL, path)


def _windows(target: Path, *, refresh: bool) -> None:
    binary = target / "whisper-cli.exe"
    if binary.is_file() and not refresh:
        print(f"reusing {binary}")
        return
    with tempfile.TemporaryDirectory(prefix="videoflow-whisper-") as temp:
        archive = Path(temp) / "whisper.zip"
        _download(WINDOWS_URL, archive)
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                name = Path(member).name
                if (
                    name in {"whisper-cli.exe", "whisper.dll"} or name.startswith("ggml")
                ) and name.endswith((".dll", ".exe")):
                    with bundle.open(member) as source, (target / name).open("wb") as output:
                        shutil.copyfileobj(source, output)
    binary.chmod(0o755)


def _linux(target: Path, *, refresh: bool) -> None:
    binary = target / "whisper-cli"
    if binary.is_file() and not refresh:
        print(f"reusing {binary}")
        return
    if shutil.which("cmake") is None:
        raise SystemExit("cmake is required to build whisper.cpp on Linux")
    with tempfile.TemporaryDirectory(prefix="videoflow-whisper-") as temp:
        work = Path(temp)
        archive = work / "whisper.tar.gz"
        _download(SOURCE_URL, archive)
        with tarfile.open(archive) as source:
            source.extractall(work, filter="data")
        source_dir = next(
            path for path in work.iterdir() if path.is_dir() and "whisper" in path.name
        )
        build = source_dir / "build"
        _run(
            [
                "cmake",
                "-B",
                str(build),
                "-DCMAKE_BUILD_TYPE=Release",
                "-DBUILD_SHARED_LIBS=OFF",
                "-DGGML_OPENMP=OFF",
                "-DCMAKE_EXE_LINKER_FLAGS=-static-libstdc++ -static-libgcc",
                "-DWHISPER_BUILD_TESTS=OFF",
                "-DWHISPER_BUILD_EXAMPLES=ON",
                "-DWHISPER_BUILD_SERVER=OFF",
            ],
            cwd=source_dir,
        )
        _run(
            [
                "cmake",
                "--build",
                str(build),
                "--config",
                "Release",
                "--target",
                "whisper-cli",
                "-j",
                str(os.cpu_count() or 1),
            ],
            cwd=source_dir,
        )
        built = build / "bin" / "whisper-cli"
        if not built.is_file():
            built = build / "bin" / "main"
        if not built.is_file():
            raise SystemExit(f"whisper.cpp did not produce a CLI: {built}")
        shutil.copy2(built, binary)
    binary.chmod(0o755)


def _download(url: str, target: Path) -> None:
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)
    print(f"wrote {target} ({target.stat().st_size / 1_000_000:.1f} MB)")


def _run(command: list[str], *, cwd: Path) -> None:
    print("running:", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch whisper.cpp and ggml-tiny.bin.")
    parser.add_argument(
        "--platform",
        choices=("auto", "linux", "windows"),
        default="auto",
        help="Target platform; auto uses the current OS.",
    )
    parser.add_argument("--dest", default=str(ROOT / "vendor"), help="Vendor directory.")
    parser.add_argument("--refresh", action="store_true", help="Download again.")
    args = parser.parse_args()
    platform = args.platform
    if platform == "auto":
        platform = "windows" if os.name == "nt" else "linux"
    fetch(platform, Path(args.dest).resolve(), refresh=args.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
