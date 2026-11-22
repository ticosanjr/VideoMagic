"""Asset license ledger persistence and review state."""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoflow.domains.media.models import AssetCandidate


def _expired(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        deadline = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return deadline < datetime.now(UTC)


def _blocked(record: dict[str, Any]) -> bool:
    return (
        record.get("license_status") in {"unknown", "cc_review", "quarantined"}
        or (record.get("license_status") == "fair_use_review" and not record.get("approved"))
        or _expired(record.get("expires_at"))
    )


def _record_paths(record: dict[str, Any], root: Path | None = None) -> set[str]:
    values: set[str] = set()
    for key in ("path", "title", "local_path", "asset_path", "downloaded_path"):
        value = str(record.get(key) or "").strip()
        if not value:
            continue
        candidate = Path(value).expanduser()
        if root is not None and not candidate.is_absolute():
            candidate = Path(root).expanduser() / candidate
        with contextlib.suppress(OSError):
            values.add(str(candidate.resolve()))
        values.add(candidate.name)
    return values


def referenced_asset_paths(output: Path, state: Any | None = None) -> set[str]:
    """Paths actually used by the timeline, overlays, B-roll, and audio plan."""

    root = Path(output).expanduser()
    values: set[str] = set()
    if state is not None:
        media = getattr(state, "media_info", None)
        if media is not None and getattr(media, "source_path", ""):
            values.add(str(Path(media.source_path).expanduser().resolve()))
        for source in (getattr(state, "sources", {}) or {}).values():
            path = getattr(source, "source_path", "")
            if path:
                values.add(str(Path(path).expanduser().resolve()))
        for overlay in getattr(state, "overlays", []) or []:
            values.add(str(Path(overlay.path).expanduser().resolve()))
        for segment in getattr(state, "video_segments", []) or []:
            clip_media = state.video_media(segment) if hasattr(state, "video_media") else None
            if clip_media is not None:
                values.add(str(Path(clip_media.source_path).expanduser().resolve()))
        for segment in getattr(state, "audio_segments", []) or []:
            clip_media = state.audio_media(segment) if hasattr(state, "audio_media") else None
            if clip_media is not None:
                values.add(str(Path(clip_media.source_path).expanduser().resolve()))
    for relative in ("broll-matches.json", "broll.json", "shorts.json", "audio/beatmap.json"):
        path = root / relative
        if not path.is_file():
            continue
        with contextlib.suppress(OSError, ValueError):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for value in _iter_paths(payload):
                candidate = Path(value).expanduser()
                if not candidate.is_absolute():
                    candidate = root / candidate
                with contextlib.suppress(OSError):
                    values.add(str(candidate.resolve()))
    return values


def _iter_paths(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                key in {"path", "local_path", "asset_path", "downloaded_path"}
                and isinstance(item, str)
            ):
                yield item
            else:
                yield from _iter_paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_paths(item)


def ledger_payload(candidates: Iterable[AssetCandidate]) -> dict[str, Any]:
    records = [candidate.to_dict() for candidate in candidates]
    blockers = [record for record in records if _blocked(record)]
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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Asset licenses", ""]
    for record in payload["assets"]:
        expiry = f" — expires {record['expires_at']}" if record.get("expires_at") else ""
        lines.append(
            f"- **{record['title']}** — {record['license_status']} — "
            f"{record['license'] or 'no license metadata'} — {record['page_url']}{expiry}"
        )
    if payload["blockers"]:
        lines.extend(
            [
                "",
                "## Needs review",
                *[f"- {item['title']} ({item['license_status']})" for item in payload["blockers"]],
            ]
        )
    (directory / "licenses.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def read_ledger(output: Path) -> dict[str, Any]:
    path = Path(output) / "assets" / "licenses.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"assets": [], "blockers": []}
    return payload if isinstance(payload, dict) else {"assets": [], "blockers": []}


def _workspace_blockers(
    output: Path,
    referenced: set[str] | None = None,
) -> list[dict[str, Any]]:
    try:
        from vf_shared.contracts.assets import iter_assets
        from vf_shared.contracts.workspace import project_dir, validate_project_id

        record_path = Path(output) / "project.json"
        payload = json.loads(record_path.read_text(encoding="utf-8"))
        project_id = validate_project_id(str(payload.get("project_id") or ""))
    except (OSError, ValueError, TypeError):
        return []
    folder = project_dir(project_id)
    names = {Path(item).name for item in referenced or ()}
    blockers: list[dict[str, Any]] = []
    for asset in iter_assets(project_id):
        if referenced is not None:
            candidate = Path(str(asset.path)).expanduser()
            if not candidate.is_absolute():
                candidate = folder / candidate
            with contextlib.suppress(OSError):
                candidate = candidate.resolve()
            if str(candidate) not in referenced and candidate.name not in names:
                continue
        if asset.license == "unknown":
            status = "unknown"
        elif asset.license == "youtube_fair_use":
            status = "fair_use_review"
        else:
            status = "clear"
        item = {
            "title": asset.path,
            "license_status": status,
            "license": asset.license,
            "page_url": asset.url,
            "approved": False,
            "source": asset.source,
        }
        if _blocked(item):
            blockers.append(item)
    return blockers


def license_blockers(
    output: Path,
    state: Any | None = None,
    *,
    scope: str = "timeline",
) -> list[dict[str, Any]]:
    """Return blockers; with a state, only assets used by that project count."""

    payload = read_ledger(output)
    referenced = (
        referenced_asset_paths(Path(output), state)
        if state is not None and scope == "timeline"
        else None
    )
    ledger = [
        record
        for record in payload.get("assets", [])
        if isinstance(record, dict)
        and _blocked(record)
        and (
            referenced is None
            or bool(_record_paths(record, Path(output)) & referenced)
        )
    ]
    return [*ledger, *_workspace_blockers(output, referenced)]


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
                f"{record.get('notes', '')}\nApproved by {reviewer or 'human'} at {approval_id}."
            ).strip()
    payload["blockers"] = [
        record
        for record in payload.get("assets", [])
        if isinstance(record, dict) and _blocked(record)
    ]
    payload["counts"] = {
        status: sum(1 for item in payload.get("assets", []) if item.get("license_status") == status)
        for status in sorted(
            {str(item.get("license_status") or "unknown") for item in payload.get("assets", [])}
        )
    }
    return write_ledger_from_payload(output, payload)


def write_ledger_from_payload(output: Path, payload: dict[str, Any]) -> Path:
    path = Path(output) / "assets" / "licenses.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
