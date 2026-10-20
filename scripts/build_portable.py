"""Build the portable onefile executable.

Linux and Windows must each build their own binary; PyInstaller does not cross
compile. Run this script on the target operating system.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dist/videoflow for this OS.")
    parser.add_argument(
        "--with-ffmpeg",
        action="store_true",
        help="Copy the local ffmpeg and ffprobe into the binary.",
    )
    parser.add_argument(
        "--fetch-ffmpeg",
        action="store_true",
        help="Download static ffmpeg and ffprobe, then bundle them (reuses vendor/).",
    )
    parser.add_argument(
        "--refresh-ffmpeg",
        action="store_true",
        help="Force a fresh static FFmpeg download.",
    )
    parser.add_argument(
        "--with-whisper",
        action="store_true",
        help="Bundle whisper-cli and the tiny GGML model (downloads/builds as needed).",
    )
    parser.add_argument(
        "--refresh-whisper",
        action="store_true",
        help="Force a fresh whisper.cpp/model download.",
    )
    parser.add_argument("--name", default="videoflow")
    parser.add_argument("--clean", action="store_true", default=True)
    args = parser.parse_args()

    vendor = ROOT / "vendor"
    if args.fetch_ffmpeg:
        suffix = ".exe" if os.name == "nt" else ""
        present = all((vendor / f"{name}{suffix}").is_file() for name in ("ffmpeg", "ffprobe"))
        if present and not args.refresh_ffmpeg:
            print("reusing vendor/ffmpeg and vendor/ffprobe")
        else:
            from fetch_ffmpeg import fetch

            fetch("windows" if os.name == "nt" else "linux", vendor)
    elif args.with_ffmpeg:
        vendor.mkdir(exist_ok=True)
        for name in ("ffmpeg", "ffprobe"):
            binary = _resolve_binary(name)
            if binary is None:
                print(
                    f"{name} was not found. Install FFmpeg, use --fetch-ffmpeg, "
                    "or place it in vendor/.",
                    file=sys.stderr,
                )
                return 1
            target = vendor / f"{name}{'.exe' if os.name == 'nt' else ''}"
            shutil.copy2(binary, target)
            if os.name != "nt":
                target.chmod(0o755)
            print(f"bundled {name}: {target} ({target.stat().st_size / 1_000_000:.1f} MB)")

    ui = ROOT / "ui" / "build"
    if not (ui / "index.html").is_file():
        print("UI build is missing; the executable will run without a browser UI.")
        print("Run `npm ci && npm run build` in ui/ to include it.")

    if args.with_whisper:
        from fetch_whisper import fetch

        whisper = vendor / "whisper"
        present = (whisper / ("whisper-cli.exe" if os.name == "nt" else "whisper-cli")).is_file()
        if present and not args.refresh_whisper:
            print(f"reusing {whisper}")
        else:
            fetch("windows" if os.name == "nt" else "linux", vendor, refresh=args.refresh_whisper)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(ROOT / "packaging" / "videoflow.spec"),
    ]
    print("running:", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        return completed.returncode

    name = f"{args.name}{'.exe' if os.name == 'nt' else ''}"
    output = ROOT / "dist" / name
    if not output.is_file():
        print(f"expected artifact is missing: {output}", file=sys.stderr)
        return 1
    print(f"built: {output} ({output.stat().st_size / 1_000_000:.1f} MB)")
    print("smoke: run the binary with `version`, `doctor`, and `demo`.")
    return 0


def _resolve_binary(name: str) -> str | None:
    if os.name == "nt":
        suffix = ".exe"
        candidates = []
        chocolatey = Path(
            os.environ.get("ChocolateyInstall", "C:/ProgramData/chocolatey")  # noqa: SIM112
        )
        candidates.append(
            chocolatey / "lib" / "ffmpeg" / "tools" / "ffmpeg" / "bin" / f"{name}{suffix}"
        )
        candidates.append(
            chocolatey / "lib" / "ffmpeg-full" / "tools" / "ffmpeg" / "bin" / f"{name}{suffix}"
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return shutil.which(name)


if __name__ == "__main__":
    raise SystemExit(main())
