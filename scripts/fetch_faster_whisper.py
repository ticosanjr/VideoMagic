"""Fetch the pinned Faster-Whisper small model for local quality transcription.

The CTranslate2 model is ~484 MB and is never downloaded implicitly by the
application. The revision and every file hash are pinned so a corrupted or
substituted download is rejected.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "Systran/faster-whisper-small"
MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
MODEL_FILES = {
    "config.json": (
        2370,
        "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828",
    ),
    "tokenizer.json": (
        2203239,
        "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab",
    ),
    "vocabulary.txt": (
        459861,
        "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913",
    ),
    "model.bin": (
        483546902,
        "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
    ),
}
DEST = ROOT / "vendor" / "faster-whisper" / "small"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the pinned Faster-Whisper small model.")
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEST,
        help="Destination directory (default vendor/faster-whisper/small).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Download even when the local files already match their hashes.",
    )
    args = parser.parse_args()
    fetch(args.dest, refresh=args.refresh)
    return 0


def fetch(dest: Path = DEST, *, refresh: bool = False) -> Path:
    target = dest.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    for name, (size, digest) in MODEL_FILES.items():
        destination = target / name
        if not refresh and _matches(destination, size, digest):
            print(f"reusing {destination}")
            continue
        _download(name, size, digest, destination)
    print(f"faster-whisper small model ready in {target}")
    return target


def _download(name: str, size: int, digest: str, destination: Path) -> None:
    url = (
        f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}"
    )
    print(f"downloading {url}")
    with tempfile.TemporaryDirectory(
        prefix="videoflow-faster-whisper-", dir=destination.parent
    ) as temp:
        download = Path(temp) / name
        with urllib.request.urlopen(url, timeout=600) as response, download.open("wb") as out:
            shutil.copyfileobj(response, out)
        _verify(download, size, digest)
        download.replace(destination)


def _matches(path: Path, size: int, digest: str) -> bool:
    return path.is_file() and path.stat().st_size == size and _sha256(path) == digest


def _verify(path: Path, size: int, digest: str) -> None:
    actual_size = path.stat().st_size
    if actual_size != size:
        raise SystemExit(f"{path.name}: expected {size} bytes, got {actual_size}")
    actual_digest = _sha256(path)
    if actual_digest != digest:
        raise SystemExit(f"{path.name}: expected sha256 {digest}, got {actual_digest}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
