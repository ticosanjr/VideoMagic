#!/usr/bin/env python
"""Build the tokenless public Windows GPU worker kit for a release."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from videoflow import __version__  # noqa: E402
from videoflow.application.win_worker_kit import build_public_worker_kit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--json-out", type=Path, default=ROOT / "dist" / "windows-kit.json")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    result = build_public_worker_kit(output=args.output)
    checksum = hashlib.sha256(result.path.read_bytes()).hexdigest()
    payload = {
        "version": __version__,
        "path": str(result.path),
        "name": result.path.name,
        "bytes": result.bytes,
        "sha256": checksum,
        "public": True,
        "token_included": False,
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (result.path.with_name(f"{result.path.name}.sha256")).write_text(
        f"{checksum}  {result.path.name}\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
