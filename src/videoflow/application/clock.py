"""Shared UTC timestamps for persisted records."""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def now_iso_ms() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def now_utc() -> datetime:
    return datetime.now(UTC)
