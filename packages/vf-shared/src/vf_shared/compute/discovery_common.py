"""Merge helpers shared by beacon and subnet discovery."""

from __future__ import annotations

from typing import Any


def _merge_workers(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for item in group:
            key = str(item.get("worker_id") or item.get("url") or "")
            if not key:
                continue
            current = merged.get(key)
            if current is None or len(item) > len(current):
                merged[key] = item
    return sorted(
        merged.values(),
        key=lambda item: (
            str(item.get("worker_id") or ""),
            str(item.get("url") or ""),
        ),
    )
