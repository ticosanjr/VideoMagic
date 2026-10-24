"""Scheduled SQLite backups with retention."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from videoflow.application import database
from videoflow.runtime import portable_home

PREFIX = "videoflow-"


def backups_dir() -> Path:
    directory = portable_home() / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def scheduled_backup(*, keep: int = 7, directory: Path | None = None) -> Path:
    """Write a timestamped snapshot and prune everything beyond ``keep``."""

    target_dir = Path(directory) if directory is not None else backups_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"{PREFIX}{stamp}.zip"
    database.backup(target)
    prune_backups(keep=keep, directory=target_dir)
    return target


def prune_backups(*, keep: int = 7, directory: Path | None = None) -> list[Path]:
    target_dir = Path(directory) if directory is not None else backups_dir()
    bundles = sorted(target_dir.glob(f"{PREFIX}*.zip"))
    if len(bundles) <= keep:
        return []
    removed = bundles[: len(bundles) - keep]
    for path in removed:
        path.unlink(missing_ok=True)
    return removed
