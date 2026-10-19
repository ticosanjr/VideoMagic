"""Stage a portable release under ``releases/v<version>/``.

The binary stays local and is uploaded as a GitHub Release asset. Only the
checksums, manifest, and notes are committed, because GitHub rejects files over
100 MB in normal git history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASES = ROOT / "releases"


def platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        machine = "x86_64"
    return f"{system}-{machine}"


def main() -> int:
    from videoflow import __version__

    parser = argparse.ArgumentParser(description="Stage a release folder.")
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--binary", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    binary = args.binary
    if binary is None:
        name = "videoflow.exe" if os.name == "nt" else "videoflow"
        binary = ROOT / "dist" / name
    if not binary.is_file():
        print(f"binary not found: {binary}")
        return 1

    target_dir = RELEASES / f"v{args.version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if os.name == "nt" else ""
    asset_name = f"videoflow-{platform_tag()}{suffix}"
    target = target_dir / asset_name
    if target.exists() and not args.force:
        print(f"asset already exists: {target} (use --force)")
        return 1
    shutil.copy2(binary, target)

    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    checksum = digest.hexdigest()
    (target_dir / "SHA256SUMS").write_text(f"{checksum}  {asset_name}\n", encoding="utf-8")
    manifest = {
        "version": args.version,
        "platform": platform_tag(),
        "asset": asset_name,
        "sha256": checksum,
        "size_bytes": target.stat().st_size,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "python": platform.python_version(),
    }
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    notes = target_dir / "release-notes.md"
    if not notes.exists():
        notes.write_text(
            f"""# VideoFlow {args.version}

Portable, model-free pre-edit pipeline.

## Artifact

- `{asset_name}`
- SHA-256: `{checksum}`

## Run

```bash
./{asset_name} doctor
./{asset_name} demo -o demo
./{asset_name} run input.mp4 -o project
./{asset_name} serve
./{asset_name} mcp
```

Windows assets are built by the `portable` CI workflow on `windows-latest`.

## Notes

See `CHANGELOG.md` for the full list of changes.
""",
            encoding="utf-8",
        )
    print(f"staged {target}")
    print(f"sha256 {checksum}")
    print(f"size   {target.stat().st_size / 1_000_000:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
