"""Project asset review helpers used by the ``vf_assets`` MCP tool."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from videoflow.application.asset_providers.ledger import (
    _blocked,
    _record_paths,
    read_ledger,
    referenced_asset_paths,
    write_ledger_from_payload,
)
from videoflow.domain.errors import AssetNotFoundError


def _workspace_records(project_id: str) -> list[dict[str, Any]]:
    try:
        from vf_shared.contracts.assets import iter_assets

        return [asset.model_dump(mode="json") for asset in iter_assets(project_id)]
    except Exception:  # noqa: BLE001 - workspace index is optional
        return []


def asset_records(
    output: Path,
    *,
    project_id: str = "",
    state: Any | None = None,
) -> list[dict[str, Any]]:
    root = Path(output).expanduser()
    referenced = referenced_asset_paths(root, state) if state is not None else None
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, items in (
        ("ledger", read_ledger(root).get("assets", [])),
        ("workspace", _workspace_records(project_id) if project_id else []),
    ):
        for item in items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("local_path") or "")
            asset_id = str(item.get("asset_id") or item.get("id") or path)
            key = asset_id or path
            if not key or key in seen:
                continue
            seen.add(key)
            paths = _record_paths(item, root)
            record = {
                **item,
                "asset_id": asset_id,
                "source": item.get("source") or source,
                "referenced": bool(referenced is not None and paths & referenced),
                "blocked": bool(_blocked(item)),
            }
            records.append(record)
    return records


def _matches(record: dict[str, Any], identifiers: Iterable[str]) -> bool:
    wanted = {str(item) for item in identifiers}
    if not wanted:
        return False
    values = {
        str(record.get("asset_id") or ""),
        str(record.get("id") or ""),
        str(record.get("path") or ""),
        str(record.get("local_path") or ""),
        str(record.get("title") or ""),
        Path(str(record.get("path") or "")).name,
    }
    return bool(values & wanted)


def review_assets(
    output: Path,
    *,
    action: str,
    project_id: str = "",
    asset_ids: list[str] | None = None,
    license: str = "",
    attribution: str = "",
    reason: str = "",
) -> dict[str, Any]:
    root = Path(output).expanduser()
    payload = read_ledger(root)
    records = payload.get("assets")
    if not isinstance(records, list):
        records = []
    ids = [str(item) for item in (asset_ids or [])]
    if action in {"approve", "quarantine"} and not ids:
        raise AssetNotFoundError("asset_ids is required")
    changed: list[str] = []
    for record in records:
        if not isinstance(record, dict) or not _matches(record, ids):
            continue
        if action == "approve":
            record["license_status"] = "clear"
            record["approved"] = True
            if license:
                record["license"] = license
            if attribution:
                record["attribution"] = attribution
        else:
            record["license_status"] = "quarantined"
            record["approved"] = False
            if reason:
                record["quarantine_reason"] = reason
        changed.append(str(record.get("asset_id") or record.get("title") or ""))
    if action == "approve" and not changed:
        # Reviewing a workspace-only asset should still persist an explicit
        # ledger decision so the export gate can see it.
        workspace = _workspace_records(project_id) if project_id else []
        for item in workspace:
            if _matches(item, ids):
                record = {
                    **item,
                    "license_status": "clear",
                    "approved": True,
                    "license": license or item.get("license") or "unknown",
                    "attribution": attribution,
                }
                records.append(record)
                changed.append(str(record.get("asset_id") or record.get("title") or ""))
    if not changed:
        raise AssetNotFoundError(f"Unknown asset ids: {', '.join(ids)}")
    payload["assets"] = records
    payload["blockers"] = [
        item for item in records if isinstance(item, dict) and _blocked(item)
    ]
    write_ledger_from_payload(root, payload)
    return {"ok": True, "action": action, "changed": changed, "count": len(changed)}
