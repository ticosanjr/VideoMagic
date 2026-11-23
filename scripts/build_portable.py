"""Build the portable onefile executable.

Linux and Windows must each build their own binary; PyInstaller does not cross
compile. Run this script on the target operating system.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ensure_ui_build() -> bool:
    """Rebuild the Svelte UI and reject a bundle with the wrong version."""

    ui = ROOT / "ui"
    package_file = ui / "package.json"
    if not package_file.is_file():
        print("UI package.json is missing", file=sys.stderr)
        return False
    try:
        version = str(json.loads(package_file.read_text(encoding="utf-8"))["version"])
    except (KeyError, ValueError) as exc:
        print(f"UI version could not be read: {exc}", file=sys.stderr)
        return False
    if not (ui / "node_modules").is_dir():
        print("ui/node_modules is missing; run npm ci before building", file=sys.stderr)
        return False
    completed = subprocess.run(
        "npm run build",
        cwd=ui,
        shell=True,
        check=False,
    )
    if completed.returncode != 0:
        print("UI build failed", file=sys.stderr)
        return False
    build = ui / "build"
    if not build.is_dir() or not any(
        version in path.read_text(encoding="utf-8", errors="ignore")
        for path in build.rglob("*.js")
    ):
        print(
            f"UI build is stale: expected version {version} in the built JS",
            file=sys.stderr,
        )
        return False
    return True


def _preload_cuda_dlls() -> None:
    """Make NVIDIA pip DLL directories visible before importing CTranslate2."""

    if os.name != "nt":
        return
    import site

    roots = [Path(item) for item in site.getsitepackages()]
    for root in roots:
        nvidia = root / "nvidia"
        if not nvidia.is_dir():
            continue
        for path in sorted(nvidia.glob("*/bin")):
            if not path.is_dir():
                continue
            with contextlib.suppress(AttributeError, OSError):
                os.add_dll_directory(str(path))
            os.environ["PATH"] = str(path) + os.pathsep + os.environ.get("PATH", "")


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
    parser.add_argument(
        "--whisper-vulkan",
        action="store_true",
        help="Build whisper.cpp with the Vulkan backend (requires glslc).",
    )
    parser.add_argument(
        "--with-silero",
        action="store_true",
        help="Bundle the pinned Silero VAD ONNX model and ONNX Runtime.",
    )
    parser.add_argument(
        "--refresh-silero",
        action="store_true",
        help="Force a fresh Silero model download.",
    )
    parser.add_argument(
        "--with-faster-whisper",
        action="store_true",
        help="Bundle Faster-Whisper, CTranslate2, PyAV, and the pinned small model.",
    )
    parser.add_argument(
        "--faster-whisper-runtime",
        action="store_true",
        help="Bundle the Faster-Whisper/CTranslate2 runtime without a model.",
    )
    parser.add_argument(
        "--with-cuda",
        action="store_true",
        help="Bundle the CTranslate2 CUDA runtime and required NVIDIA DLLs.",
    )
    parser.add_argument(
        "--refresh-faster-whisper",
        action="store_true",
        help="Force a fresh Faster-Whisper small model download.",
    )
    parser.add_argument(
        "--with-tray",
        action="store_true",
        help="Bundle pystray, Pillow, and python-xlib for the desktop tray icon.",
    )
    parser.add_argument(
        "--with-models",
        action="store_true",
        help="Bundle speech model weights. Off by default for the lean download.",
    )
    parser.add_argument("--name", default="videoflow")
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build a directory bundle instead of a onefile executable.",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Zip the onedir bundle after a successful build (stored, fast).",
    )
    parser.add_argument(
        "--zip-name",
        default="",
        help="Zip file name under dist/ (default: VideoFlow-<version>-<platform>.zip).",
    )
    parser.add_argument(
        "--clean",
        dest="clean",
        action="store_true",
        default=False,
        help="Force a cold PyInstaller build and clear its analysis cache.",
    )
    parser.add_argument(
        "--no-clean",
        dest="clean",
        action="store_false",
        help="Reuse the PyInstaller cache (default).",
    )
    parser.add_argument(
        "--runtime-base",
        type=Path,
        default=None,
        help="After an onedir build, keep a hardlinked runtime at this path.",
    )
    parser.add_argument(
        "--skip-ui-build",
        action="store_true",
        help="Do not rebuild the Svelte UI before packaging (not recommended).",
    )
    args = parser.parse_args()
    if args.zip and not args.onedir:
        parser.error("--zip requires --onedir")
    if args.zip_name and not args.zip:
        parser.error("--zip-name requires --zip")
    if not args.skip_ui_build and not ensure_ui_build():
        return 1

    vendor = ROOT / "vendor"
    if args.fetch_ffmpeg:
        suffix = ".exe" if os.name == "nt" else ""
        present = all((vendor / f"{name}{suffix}").is_file() for name in ("ffmpeg", "ffprobe"))
        if present and not args.refresh_ffmpeg:
            print("reusing vendor/ffmpeg and vendor/ffprobe")
        else:
            from fetch_ffmpeg import fetch as fetch_ffmpeg

            fetch_ffmpeg("windows" if os.name == "nt" else "linux", vendor)
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
        whisper = vendor / "whisper"
        present = (whisper / ("whisper-cli.exe" if os.name == "nt" else "whisper-cli")).is_file()
        if present and not args.refresh_whisper:
            print(f"reusing {whisper}")
        else:
            fetch(
                "windows" if os.name == "nt" else "linux",
                vendor,
                refresh=args.refresh_whisper,
                vulkan=args.whisper_vulkan,
            )

    if args.with_silero:
        completed = subprocess.run(
            [sys.executable, "-c", "import onnxruntime"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            print(
                "onnxruntime is required for --with-silero. Run `uv sync` first.",
                file=sys.stderr,
            )
            return 1
        from fetch_silero import fetch as fetch_silero

        fetch_silero(vendor, refresh=args.refresh_silero)

    if args.with_tray:
        required = ["pystray", "PIL"]
        if sys.platform.startswith("linux"):
            required.append("Xlib")
        missing = [
            name for name in required if importlib.util.find_spec(name) is None
        ]
        if missing:
            print(
                "The tray extra is missing: "
                + ", ".join(missing)
                + ". Run `uv sync --extra tray` for this interpreter.",
                file=sys.stderr,
            )
            return 1
        os.environ["VIDEOWFLOW_WITH_TRAY"] = "1"
        print("bundling desktop tray dependencies: pystray, Pillow, python-xlib")

    if args.with_faster_whisper or args.refresh_faster_whisper or args.faster_whisper_runtime:
        missing = [
            name
            for name in (
                "faster_whisper",
                "ctranslate2",
                "tokenizers",
                "av",
                "huggingface_hub",
            )
            if importlib.util.find_spec(name) is None
        ]
        if missing:
            print(
                "The faster-whisper extra is missing: "
                + ", ".join(missing)
                + ". Run `uv sync --extra faster-whisper` for this interpreter.",
                file=sys.stderr,
            )
            return 1
        if args.with_faster_whisper or args.refresh_faster_whisper:
            from fetch_faster_whisper import fetch as fetch_faster_whisper

            model = fetch_faster_whisper(
                vendor / "faster-whisper" / "small",
                refresh=args.refresh_faster_whisper,
            )
            print(f"bundling Faster-Whisper model: {model}")
        else:
            print("bundling Faster-Whisper runtime without a model")
        _preload_cuda_dlls()
        import ctranslate2
        import faster_whisper

        print(
            f"faster-whisper {faster_whisper.__version__}, "
            f"CTranslate2 {ctranslate2.__version__}"
        )
        os.environ["VIDEOWFLOW_WITH_FASTER_WHISPER"] = "1"

    if args.with_cuda:
        has_runtime = (
            args.with_faster_whisper
            or args.refresh_faster_whisper
            or args.faster_whisper_runtime
        )
        if not has_runtime:
            print(
                "--with-cuda requires --faster-whisper-runtime or --with-faster-whisper",
                file=sys.stderr,
            )
            return 1
        missing = [
            name
            for name in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime")
            if importlib.util.find_spec(name) is None
        ]
        if missing:
            print(
                "The CUDA runtime is missing: "
                + ", ".join(missing)
                + ". Install nvidia-cublas-cu12, nvidia-cudnn-cu12, and "
                "nvidia-cuda-runtime-cu12.",
                file=sys.stderr,
            )
            return 1
        _preload_cuda_dlls()
        import ctranslate2

        os.environ["VIDEOWFLOW_WITH_CUDA"] = "1"
        print(
            "bundling CTranslate2 CUDA runtime; "
            f"CUDA devices visible at build time: {ctranslate2.get_cuda_device_count()}"
        )

    os.environ["VIDEOWFLOW_BUNDLE_MODELS"] = "1" if args.with_models else "0"
    os.environ["VIDEOWFLOW_ONEDIR"] = "1" if args.onedir else "0"
    os.environ["VIDEOWFLOW_NAME"] = str(args.name)

    suffix = ".exe" if os.name == "nt" else ""
    output = ROOT / "dist" / (args.name if args.onedir else f"{args.name}{suffix}")
    if args.onedir and output.is_file():
        output.unlink()
    elif not args.onedir and output.is_dir():
        shutil.rmtree(output)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
    ]
    if args.clean:
        command.append("--clean")
    command.append(str(ROOT / "packaging" / "videoflow.spec"))
    print("running:", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        return completed.returncode

    name = f"{args.name}{'.exe' if os.name == 'nt' else ''}"
    output = ROOT / "dist" / (args.name if args.onedir else name)
    if args.onedir:
        if not output.is_dir():
            print(f"expected artifact is missing: {output}", file=sys.stderr)
            return 1
        if args.runtime_base is not None:
            if args.runtime_base.exists():
                shutil.rmtree(args.runtime_base)
            shutil.copytree(output, args.runtime_base, copy_function=os.link)
            print(f"runtime base: {args.runtime_base}")
        print(f"built: {output} (onedir)")
        if args.zip:
            archive = ROOT / "dist" / (
                args.zip_name or f"VideoFlow-{_package_version()}-{_platform_tag()}.zip"
            )
            zip_directory(output, archive)
            print(
                f"built: {archive} "
                f"({archive.stat().st_size / 1_000_000:.1f} MB, stored)"
            )
    else:
        if not output.is_file():
            print(f"expected artifact is missing: {output}", file=sys.stderr)
            return 1
        print(f"built: {output} ({output.stat().st_size / 1_000_000:.1f} MB)")
    print("smoke: run scripts/smoke_windows.py --exe <artifact>.")
    return 0


def _package_version() -> str:
    try:
        from videoflow import __version__

        return __version__
    except Exception:  # noqa: BLE001 - the archive name is cosmetic
        return "dev"


def _platform_tag() -> str:
    import platform

    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        machine = "x64"
    return f"{system}-{machine}"


def zip_directory(source: Path, archive: Path) -> None:
    """Write a stored zip so a portable onedir folder ships without recompression."""

    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(source).as_posix())


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


VERSION = "v1.7.6"
SOURCE_URL = f"https://github.com/ggml-org/whisper.cpp/archive/refs/tags/{VERSION}.tar.gz"
WINDOWS_URL = (
    "https://github.com/ggml-org/whisper.cpp/releases/download/"
    f"{VERSION}/whisper-bin-x64.zip"
)
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin"


def fetch(
    platform: str, dest: Path, *, refresh: bool = False, vulkan: bool = False
) -> Path:
    target = dest / "whisper"
    target.mkdir(parents=True, exist_ok=True)
    _model(target, refresh=refresh)
    if platform == "windows":
        _windows(target, refresh=refresh)
    else:
        _linux(target, refresh=refresh, vulkan=vulkan)
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


def _linux(target: Path, *, refresh: bool, vulkan: bool = False) -> None:
    binary = target / "whisper-cli"
    marker = target / "vulkan.flag"
    if binary.is_file() and not refresh and (not vulkan or marker.is_file()):
        print(f"reusing {binary}")
        return
    if shutil.which("cmake") is None:
        raise SystemExit("cmake is required to build whisper.cpp on Linux")
    if vulkan and shutil.which("glslc") is None:
        raise SystemExit(
            "Vulkan whisper.cpp requires glslc (shaderc). Install glslc or "
            "run without --vulkan."
        )
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
        configure = [
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
        ]
        if vulkan:
            configure.insert(4, "-DGGML_VULKAN=ON")
        _run(configure, cwd=source_dir)
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
        marker = target / "vulkan.flag"
        if vulkan:
            marker.write_text("vulkan\n", encoding="utf-8")
        else:
            marker.unlink(missing_ok=True)
    binary.chmod(0o755)


def _download(url: str, target: Path) -> None:
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)
    print(f"wrote {target} ({target.stat().st_size / 1_000_000:.1f} MB)")


def _run(command: list[str], *, cwd: Path) -> None:
    print("running:", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
