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

datas = [(str(ROOT / "src" / "videoflow" / "presets"), "videoflow/presets")]
binaries = []
hiddenimports = [
    "videoflow.api",
    "videoflow.api.app",
    "videoflow.mcp_server",
    "videoflow.mcp_server.server",
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

if os.environ.get("VIDEOWFLOW_WITH_FASTER_WHISPER") == "1":
    for package in ("faster_whisper", "ctranslate2", "tokenizers", "av", "huggingface_hub"):
        try:
            package_datas, package_binaries, package_hidden = collect_all(package)
            datas += package_datas
            binaries += package_binaries
            hiddenimports += package_hidden
        except Exception as error:
            raise SystemExit(f"cannot bundle {package}: {error}") from error
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
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="videoflow",
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
)
