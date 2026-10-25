"""Keep the Python package, UI package, and release version in lockstep."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    args = parser.parse_args()
    version = args.version.strip().lstrip("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"Invalid version: {version}")

    pyproject = ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    text = re.sub(r'^version = "[^"]+"', f'version = "{version}"', text, count=1, flags=re.M)
    pyproject.write_text(text, encoding="utf-8")

    init = ROOT / "src" / "videoflow" / "__init__.py"
    text = re.sub(
        r'__version__ = "[^"]+"',
        f'__version__ = "{version}"',
        init.read_text(encoding="utf-8"),
        count=1,
    )
    init.write_text(text, encoding="utf-8")

    package = ROOT / "ui" / "package.json"
    payload = json.loads(package.read_text(encoding="utf-8"))
    payload["version"] = version
    package.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"version set to {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
