"""Stage portable release artifacts under ``releases/v<version>/``.

The binaries stay local and are uploaded to a GitHub Release manually. Only the
checksums, manifest, and notes are committed, because GitHub rejects files over
100 MB in normal git history. The three newest version folders are kept by
default; older folders are pruned after a successful stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASES = ROOT / "releases"
_VERSION_DIR = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def _release_key(path: Path) -> tuple[int, int, int] | None:
    match = _VERSION_DIR.fullmatch(path.name)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _prune_old_releases(root: Path, keep: int = 3) -> list[Path]:
    if keep < 1:
        raise ValueError("keep must be at least 1")
    versioned: list[tuple[tuple[int, int, int], Path]] = []
    for path in root.iterdir():
        key = _release_key(path)
        if path.is_dir() and key is not None:
            versioned.append((key, path))
    versioned.sort(key=lambda item: item[0])
    stale = [path for _, path in versioned[:-keep]] if len(versioned) > keep else []
    for path in stale:
        shutil.rmtree(path)
    return stale


def default_artifacts(version: str) -> tuple[tuple[Path, str], ...]:
    return (
        (ROOT / "dist" / "videoflow", f"videoflow-{version}-linux-x86_64"),
        (
            ROOT / "dist" / f"VideoFlow-{version}-x86_64.AppImage",
            f"VideoFlow-{version}-x86_64.AppImage",
        ),
        (ROOT / "dist" / "videoflow.exe", f"videoflow-{version}-windows-x86_64.exe"),
        (ROOT / "dist" / "sbom.json", "sbom.json"),
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
        "--keep",
        type=int,
        default=3,
        help="Keep this many newest release folders (default: 3).",
    )
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Fail if a default artifact is missing.",
    )
    args = parser.parse_args()
    if args.keep < 1:
        parser.error("--keep must be at least 1")

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
        notes.write_text(_release_notes(args.version, staged), encoding="utf-8")
    removed = _prune_old_releases(RELEASES, keep=args.keep)
    for path in removed:
        print(f"pruned {path}")
    print(f"release staged in {target_dir} (keeping {args.keep} versions)")
    return 0


def _release_notes(version: str, staged: list[dict[str, object]]) -> str:
    """Describe only the artifacts that were actually staged."""

    listing = "\n".join(f"- `{item['name']}` — SHA-256 `{item['sha256']}`" for item in staged)
    names = {str(item["name"]) for item in staged}
    linux = next((name for name in names if name.endswith("linux-x86_64")), None)
    appimage = next((name for name in names if name.endswith(".AppImage")), None)
    windows = next((name for name in names if name.endswith(".exe")), None)
    sections: list[str] = []
    if linux:
        sections.append(
            "Linux plain binary:\n\n"
            "```bash\n"
            f"./{linux} doctor\n"
            f"./{linux} recipe list\n"
            f"./{linux} recipe run youtube_talking_head input.mp4 -o project\n"
            "```"
        )
    if appimage:
        sections.append(
            "Linux AppImage (no FUSE required with extract-and-run):\n\n"
            "```bash\n"
            f"chmod +x {appimage}\n"
            f"./{appimage} version\n"
            f"./{appimage} recipe list\n"
            "```"
        )
    if windows:
        sections.append(
            "Windows:\n\n"
            "```powershell\n"
            f".\\{windows} version\n"
            f".\\{windows} doctor\n"
            f".\\{windows} recipe list\n"
            "```\n\n"
            "The Windows artifact is PE32+ x86-64 and was smoke-tested under Wine."
        )
    return (
        f"# VideoFlow {version}\n\n"
        "Portable video pre-edit pipeline with offline whisper.cpp transcription.\n\n"
        "## Artifacts\n\n"
        f"{listing}\n\n"
        "## Run\n\n"
        f"{(chr(10) * 2).join(sections)}\n\n"
        "## Notes\n\n"
        "See `CHANGELOG.md`.\n"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
