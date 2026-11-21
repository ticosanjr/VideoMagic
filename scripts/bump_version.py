"""Set the application version in the manifests and code package."""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _replace(path: Path, pattern: re.Pattern[str], replacement: str) -> bool:
    text = path.read_text(encoding="utf-8")
    updated, count = pattern.subn(replacement, text, count=1)
    if count == 0:
        raise SystemExit(f"version pattern not found in {path}")
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def _update_changelog(version: str) -> bool:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    if f"## [{version}]" in text:
        return False
    heading = f"## [{version}] - {date.today().isoformat()}"
    if "## [Unreleased]" in text:
        updated = text.replace("## [Unreleased]", heading, 1)
    else:
        marker = "# Changelog\n\n"
        updated = text.replace(
            marker,
            f"{marker}{heading}\n\n- Release {version}.\n\n",
            1,
        )
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: bump_version.py X.Y.Z", file=sys.stderr)
        return 2
    version = sys.argv[1].strip()
    if not VERSION_RE.fullmatch(version):
        print(f"invalid version: {version}", file=sys.stderr)
        return 2

    changed = []
    package_manifests = (
        "gpu-worker",
        "mcp-audio",
        "mcp-fetch",
        "mcp-vision",
        "scene-rules",
        "vf-compute",
        "vf-contracts",
        "vf-shared",
    )
    targets = [
        (
            ROOT / "packages" / name / "pyproject.toml",
            re.compile(r'(?m)^version = "[^"]+"'),
            f'version = "{version}"',
        )
        for name in package_manifests
    ] + [
        (
            ROOT / "pyproject.toml",
            re.compile(r'(?m)^version = "[^"]+"'),
            f'version = "{version}"',
        ),
        (
            ROOT / "ui" / "package.json",
            re.compile(r'(?m)^  "version": "[^"]+"'),
            f'  "version": "{version}"',
        ),
        (
            ROOT / "src" / "videoflow" / "__init__.py",
            re.compile(r'(?m)^__version__ = "[^"]+"'),
            f'__version__ = "{version}"',
        ),
        (
            ROOT / "uv.lock",
            re.compile(r'(?ms)(name = "videoflow"\nversion = ")[^"]+"'),
            rf'\g<1>{version}"',
        ),
    ]
    for path, pattern, replacement in targets:
        if _replace(path, pattern, replacement):
            changed.append(path.relative_to(ROOT))
    package_lock = ROOT / "ui" / "package-lock.json"
    if package_lock.is_file():
        text = package_lock.read_text(encoding="utf-8")
        updated, count = re.subn(
            r'("version": ")[^"]+(")',
            rf'\g<1>{version}\2',
            text,
            count=2,
        )
        if count == 2 and updated != text:
            package_lock.write_text(updated, encoding="utf-8")
            changed.append(package_lock.relative_to(ROOT))
    if _update_changelog(version):
        changed.append(Path("CHANGELOG.md"))

    for path in changed:
        print(f"updated {path}")
    print(f"version set to {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
