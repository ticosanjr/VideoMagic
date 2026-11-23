# PyInstaller onefile spec for the portable VideoFlow executable.
# Build with: uv run python scripts/build_portable.py --with-ffmpeg

import os
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

ROOT = Path(SPECPATH).resolve().parent
VENDOR = Path(os.environ.get("VIDEOWFLOW_VENDOR_DIR", str(ROOT / "vendor")))
BUNDLE_MODELS = os.environ.get("VIDEOWFLOW_BUNDLE_MODELS") == "1"

datas = [
    (str(ROOT / "src" / "videoflow" / "presets"), "videoflow/presets"),
    (str(ROOT / "src" / "videoflow" / "styles"), "videoflow/styles"),
    (str(ROOT / "src" / "videoflow" / "workflows"), "videoflow/workflows"),
    (str(ROOT / "src" / "videoflow" / "templates"), "videoflow/templates"),
    (str(ROOT / "docs" / "contracts"), "docs/contracts"),
]
binaries = []
hiddenimports = [
    "videoflow.api",
    "videoflow.api.app",
    "videoflow.mcp_server",
    "videoflow.mcp_server.server",
    "scene_rules",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "mcp.server.stdio",
    "mcp.server.streamable_http",
    "mcp.server.streamable_http_manager",
    "opentimelineio.adapters",
    "opentimelineio.plugins",
]

ui_build = ROOT / "ui" / "build"
if (ui_build / "index.html").is_file():
    datas.append((str(ui_build), "ui"))

for name in ("ffmpeg", "ffprobe"):
    for suffix in ("", ".exe"):
        candidate = VENDOR / f"{name}{suffix}"
        if candidate.is_file():
            binaries.append((str(candidate), "vendor"))

silero = VENDOR / "silero"
if silero.is_dir():
    for candidate in sorted(silero.glob("*.onnx")):
        datas.append((str(candidate), "silero"))

whisper = VENDOR / "whisper"
if whisper.is_dir():
    for candidate in sorted(whisper.iterdir()):
        if not candidate.is_file():
            continue
        suffix = candidate.suffix.lower()
        if suffix == ".bin" and not BUNDLE_MODELS:
            continue
        if suffix in {".exe", ".dll", ".so", ".dylib"} or (
            suffix == "" and os.access(candidate, os.X_OK)
        ):
            binaries.append((str(candidate), "whisper"))
        else:
            datas.append((str(candidate), "whisper"))

datas += collect_data_files("mcp")
hiddenimports += collect_submodules("mcp.server")

otio_datas, otio_binaries, otio_hidden = collect_all("opentimelineio")
datas += otio_datas
binaries += otio_binaries
hiddenimports += otio_hidden

try:
    ort_datas, ort_binaries, ort_hidden = collect_all("onnxruntime")
    datas += ort_datas
    binaries += ort_binaries
    hiddenimports += ort_hidden
except Exception:
    pass

# Optional desktop/vision helpers. They are imported lazily, so PyInstaller
# needs the package data and submodules explicitly.
for package in ("PIL", "pystray", "pytesseract", "Xlib", "six", "websocket"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hidden
    except Exception:
        pass

hiddenimports += [
    "optparse",
    "websocket",
    "pystray._xorg",
    "pystray._gtk",
    "pystray._appindicator",
    "Xlib.display",
    "Xlib.threaded",
    "Xlib.XK",
]

icon = ROOT / "packaging" / "videoflow.png"
if icon.is_file():
    datas.append((str(icon), "packaging"))

if os.environ.get("VIDEOWFLOW_WITH_CUDA") == "1":
    import site
    import sysconfig

    nvidia_roots = {Path(item) for item in site.getsitepackages()}
    nvidia_roots.add(Path(sysconfig.get_paths()["purelib"]))
    cuda_dlls: list[Path] = []
    for root in nvidia_roots:
        nvidia = root / "nvidia"
        if nvidia.is_dir():
            cuda_dlls.extend(nvidia.glob("*/bin/*.dll"))
            cuda_dlls.extend(nvidia.glob("*/lib/*.dll"))
    if not cuda_dlls:
        raise SystemExit("CUDA build requested but no NVIDIA DLLs were found")
    for dll in sorted(cuda_dlls):
        binaries.append((str(dll), "nvidia"))
    flag = ROOT / "build" / "cuda.flag"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1\n", encoding="utf-8")
    datas.append((str(flag), "videoflow"))

if os.environ.get("VIDEOWFLOW_WITH_FASTER_WHISPER") == "1":
    for package in ("faster_whisper", "ctranslate2", "tokenizers", "av", "huggingface_hub"):
        try:
            package_datas, package_binaries, package_hidden = collect_all(package)
            datas += package_datas
            binaries += package_binaries
            hiddenimports += package_hidden
        except Exception as error:
            raise SystemExit(f"cannot bundle {package}: {error}") from error
    if BUNDLE_MODELS:
        model = VENDOR / "faster-whisper" / "small"
        if not (model / "model.bin").is_file() or not (model / "config.json").is_file():
            raise SystemExit(f"Faster-Whisper model is incomplete: {model}")
        datas.append((str(model), "faster-whisper/small"))

for distribution in (
    "mcp",
    "opentimelineio",
    "pydantic",
    "pydantic-core",
    "fastapi",
    "starlette",
    "uvicorn",
    "onnxruntime",
    "faster-whisper",
    "ctranslate2",
    "tokenizers",
    "av",
    "huggingface-hub",
):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        pass

analysis = Analysis(
    [str(ROOT / "src" / "videoflow" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(ROOT / "packaging" / "runtime_hooks" / "cuda_dlls.py")
    ],
    excludes=[
        "tkinter",
        "matplotlib",
        "torch",
        "torchaudio",
        "scipy",
        "pandas",
        "sklearn",
        "lightning",
        "tensorflow",
        "grpc",
        "mako",
        "pytest",
        "sqlalchemy",
        "alembic",
        "__main__",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

onedir = os.environ.get("VIDEOWFLOW_ONEDIR") == "1"
build_name = os.environ.get("VIDEOWFLOW_NAME", "videoflow")
exe = EXE(
    pyz,
    analysis.scripts,
    [] if onedir else analysis.binaries,
    [] if onedir else analysis.datas,
    [],
    name=build_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    exclude_binaries=onedir,
)

if onedir:
    COLLECT(
        exe,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        name=build_name,
    )
