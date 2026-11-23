"""Build the GPU worker and shared runtime wheels for the Windows kit.

The worker kit refuses to fall back to another version's wheel. CI must build
the exact kit version before packaging the portable bundle and the kit itself.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELS = ROOT / "src" / "videoflow" / "templates" / "wheels"
WIN_WHEELS = WHEELS / "win"


def _version() -> str:
    from videoflow import __version__

    return __version__


def _run(command: list[str]) -> None:
    print("running:", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _wheel(dist: Path, package: str, version: str) -> Path:
    matches = sorted(dist.glob(f"{package}-{version}-*.whl"))
    if not matches:
        raise SystemExit(f"missing {package} {version} wheel in {dist}")
    return matches[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and stage the worker/shared wheels for the Windows kit."
    )
    parser.add_argument(
        "--version",
        default="",
        help="Wheel version (default: the installed VideoFlow version).",
    )
    args = parser.parse_args(argv)
    version = args.version.strip() or _version()
    dist = ROOT / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    WHEELS.mkdir(parents=True, exist_ok=True)
    WIN_WHEELS.mkdir(parents=True, exist_ok=True)

    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required to build the worker wheels")
    _run([uv, "build", "packages/vf-shared", "--out-dir", str(dist)])
    _run([uv, "build", "packages/gpu-worker", "--out-dir", str(dist)])

    shared = _wheel(dist, "vf_shared", version)
    worker = _wheel(dist, "videoflow_gpu_worker", version)
    shutil.copy2(shared, WIN_WHEELS / shared.name)
    shutil.copy2(worker, WHEELS / worker.name)
    print(f"staged {shared}")
    print(f"staged {worker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
