"""Asset license ledger persistence and review state."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from videoflow.application.asset_providers.models import AssetCandidate


def ledger_payload(candidates: Iterable[AssetCandidate]) -> dict[str, Any]:
    records = [candidate.to_dict() for candidate in candidates]
    blockers = [
        record
        for record in records
        if record["license_status"] in {"unknown", "cc_review"}
        or (
            record["license_status"] == "fair_use_review"
            and not record["approved"]
        )
    ]
    return {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "assets": records,
        "blockers": blockers,
        "counts": {
            status: sum(1 for item in records if item["license_status"] == status)
            for status in sorted({item["license_status"] for item in records})
        },
    }


def write_ledger(output: Path, candidates: Iterable[AssetCandidate]) -> Path:
    payload = ledger_payload(candidates)
    directory = Path(output) / "assets"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "licenses.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = ["# Asset licenses", ""]
    for record in payload["assets"]:
        lines.append(
            f"- **{record['title']}** — {record['license_status']} — "
            f"{record['license'] or 'no license metadata'} — {record['page_url']}"
        )
    if payload["blockers"]:
        lines.extend(
            [
                "",
                "## Needs review",
                *[
                    f"- {item['title']} ({item['license_status']})"
                    for item in payload["blockers"]
                ],
            ]
        )
    (directory / "licenses.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8"
    )
    return path


def read_ledger(output: Path) -> dict[str, Any]:
    path = Path(output) / "assets" / "licenses.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"assets": [], "blockers": []}
    return payload if isinstance(payload, dict) else {"assets": [], "blockers": []}


def license_blockers(output: Path) -> list[dict[str, Any]]:
    payload = read_ledger(output)
    blockers = []
    for record in payload.get("assets", []):
        if record.get("license_status") in {"unknown", "cc_review"} or (
            record.get("license_status") == "fair_use_review"
            and not record.get("approved")
        ):
            blockers.append(record)
    return blockers


def mark_approved(output: Path, *, approval_id: str, reviewer: str = "") -> Path:
    payload = read_ledger(output)
    for record in payload.get("assets", []):
        if record.get("license_status") in {
            "fair_use_review",
            "cc_review",
            "unknown",
        }:
            record["approved"] = True
            record["approval_id"] = approval_id
            record["notes"] = (
                f"{record.get('notes', '')}\nApproved by "
                f"{reviewer or 'human'} at {approval_id}."
            ).strip()
    payload["blockers"] = [
        record
        for record in payload.get("assets", [])
        if record.get("license_status") in {"unknown", "cc_review"}
        or (
            record.get("license_status") == "fair_use_review"
            and not record.get("approved")
        )
    ]
    payload["counts"] = {
        status: sum(
            1
            for item in payload.get("assets", [])
            if item.get("license_status") == status
        )
        for status in sorted(
            {
                str(item.get("license_status") or "unknown")
                for item in payload.get("assets", [])
            }
        )
    }
    return write_ledger_from_payload(output, payload)


def write_ledger_from_payload(output: Path, payload: dict[str, Any]) -> Path:
    path = Path(output) / "assets" / "licenses.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path
