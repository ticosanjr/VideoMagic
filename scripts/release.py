"""Stage portable release artifacts under ``releases/v<version>/``.

The binaries stay local and are uploaded to a GitHub Release manually. Only the
checksums, manifest, and notes are committed, because GitHub rejects files over
100 MB in normal git history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASES = ROOT / "releases"


def default_artifacts(version: str) -> tuple[tuple[Path, str], ...]:
    return (
        (ROOT / "dist" / "videoflow", f"videoflow-{version}-linux-x86_64"),
        (
            ROOT / "dist" / f"VideoFlow-{version}-x86_64.AppImage",
            f"VideoFlow-{version}-x86_64.AppImage",
        ),
        (ROOT / "dist" / "videoflow.exe", f"videoflow-{version}-windows-x86_64.exe"),
    )


def platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        machine = "x86_64"
    return f"{system}-{machine}"


def main() -> int:
    from videoflow import __version__

    parser = argparse.ArgumentParser(description="Stage release artifacts.")
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Fail if a default artifact is missing.",
    )
    args = parser.parse_args()

    target_dir = RELEASES / f"v{args.version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    staged: list[dict[str, object]] = []
    sums: list[str] = []
    for source, asset_name in default_artifacts(args.version):
        if not source.is_file():
            if args.require_all:
                print(f"missing artifact: {source}")
                return 1
            print(f"skip missing artifact: {source}")
            continue
        target = target_dir / asset_name
        if target.exists() and not args.force:
            print(f"asset already exists: {target} (use --force)")
            return 1
        shutil.copy2(source, target)
        checksum = _sha256(target)
        sums.append(f"{checksum}  {asset_name}")
        staged.append(
            {
                "name": asset_name,
                "sha256": checksum,
                "size_bytes": target.stat().st_size,
            }
        )
        print(f"staged {target} ({target.stat().st_size / 1_000_000:.1f} MB)")

    if not staged:
        print("nothing staged")
        return 1

    (target_dir / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    manifest = {
        "version": args.version,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": platform_tag(),
        "python": platform.python_version(),
        "artifacts": staged,
    }
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    notes = target_dir / "release-notes.md"
    if not notes.exists():
        listing = "\n".join(f"- `{item['name']}` — SHA-256 `{item['sha256']}`" for item in staged)
        notes.write_text(
            f"""# VideoFlow {args.version}

Portable, model-free pre-edit pipeline.

## Artifacts

{listing}

## Run

Linux plain binary:

```bash
./videoflow-linux-x86_64 doctor
./videoflow-linux-x86_64 demo -o demo
./videoflow-linux-x86_64 run input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-x86_64.AppImage
./VideoFlow-x86_64.AppImage version
./VideoFlow-x86_64.AppImage demo -o demo
```

Windows:

```powershell
.\\videoflow-windows-x86_64.exe version
.\\videoflow-windows-x86_64.exe doctor
.\\videoflow-windows-x86_64.exe demo -o demo
```

## Notes

See `CHANGELOG.md`. Windows artifacts are PE32+ x86-64 and were built and
smoke-tested under Wine in this release.
""",
            encoding="utf-8",
        )
    print(f"release staged in {target_dir}")
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
