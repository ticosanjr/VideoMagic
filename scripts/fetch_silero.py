"""Fetch the pinned Silero VAD ONNX model for the portable build.

Silero v5.1.2 is small (~2.3 MB) and runs through ONNX Runtime on the CPU. The
model is content-addressed so a corrupted or substituted download is rejected.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v5.1.2"
MODEL_URL = (
    f"https://github.com/snakers4/silero-vad/raw/{VERSION}/src/silero_vad/data/silero_vad.onnx"
)
MODEL_SHA256 = "2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f"


def fetch(dest: Path, *, refresh: bool = False) -> Path:
    target = dest / "silero" / "silero_vad.onnx"
    if target.is_file() and not refresh and _sha256(target) == MODEL_SHA256:
        print(f"reusing {target}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {MODEL_URL}")
    with tempfile.TemporaryDirectory(prefix="videoflow-silero-", dir=target.parent) as temp:
        download = Path(temp) / "silero_vad.onnx"
        with urllib.request.urlopen(MODEL_URL, timeout=120) as response, download.open("wb") as out:
            shutil.copyfileobj(response, out)
        actual = _sha256(download)
        if actual != MODEL_SHA256:
            raise SystemExit(
                f"Silero model checksum mismatch: expected {MODEL_SHA256}, got {actual}"
            )
        download.replace(target)
    print(f"wrote {target} ({target.stat().st_size / 1_000_000:.1f} MB)")
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the pinned Silero VAD ONNX model.")
    parser.add_argument("--dest", default=str(ROOT / "vendor"), help="Vendor directory.")
    parser.add_argument("--refresh", action="store_true", help="Download again.")
    args = parser.parse_args()
    fetch(Path(args.dest).resolve(), refresh=args.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
