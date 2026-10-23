"""Persist human approval and ordering for planned B-roll per Short."""

from __future__ import annotations

import json
from pathlib import Path

from videoflow.domain.errors import StateNotReadyError

APPROVAL_FILE = "broll_approval.json"


def _path(output: Path) -> Path:
    return Path(output) / APPROVAL_FILE


def load_approvals(output: Path) -> dict[str, dict[str, list[int]]]:
    path = _path(output)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    result: dict[str, dict[str, list[int]]] = {}
    if not isinstance(payload, dict):
        return result
    for title, entry in payload.items():
        if not isinstance(entry, dict):
            continue
        approved = [int(item) for item in entry.get("approved", []) if isinstance(item, int)]
        order = [int(item) for item in entry.get("order", []) if isinstance(item, int)]
        result[str(title)] = {"approved": approved, "order": order or approved}
    return result


def save_approval(
    output: Path,
    *,
    title: str,
    approved: list[int],
    order: list[int] | None = None,
    plan: dict[str, list[dict[str, object]]] | None = None,
) -> dict[str, dict[str, list[int]]]:
    if not title.strip():
        raise StateNotReadyError("B-roll approval needs a Short title.")
    count = len((plan or {}).get(title, []))
    if count == 0 and title not in (plan or {}):
        raise StateNotReadyError(f"Unknown B-roll plan: {title}")
    clean_approved = sorted({int(item) for item in approved if 0 <= int(item) < count})
    clean_order = [int(item) for item in (order or clean_approved)]
    clean_order = [item for item in clean_order if 0 <= item < count]
    for item in clean_approved:
        if item not in clean_order:
            clean_order.append(item)
    approvals = load_approvals(output)
    approvals[title] = {"approved": clean_approved, "order": clean_order}
    path = _path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approvals, indent=2) + "\n", encoding="utf-8")
    return approvals


def ordered_entries(
    plan: dict[str, list[dict[str, object]]],
    approvals: dict[str, dict[str, list[int]]],
) -> dict[str, list[dict[str, object]]]:
    """Return only approved entries in the operator's order."""

    result: dict[str, list[dict[str, object]]] = {}
    for title, entries in plan.items():
        approval = approvals.get(title, {})
        order = [int(item) for item in approval.get("order", [])]
        if not order:
            continue
        result[title] = [entries[index] for index in order if 0 <= index < len(entries)]
    return result
