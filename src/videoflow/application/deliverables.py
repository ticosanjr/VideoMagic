"""Review approval and thumbnail variant selection for a finished job."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from videoflow.domain.errors import StateNotReadyError

REVIEW_APPROVAL = "review_approval.json"
THUMBNAIL_CHOICE = "thumbnail_choice.json"


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def review_payload(output: Path) -> dict[str, object]:
    review = _read_json(Path(output) / "review.json")
    approval = _read_json(Path(output) / REVIEW_APPROVAL)
    return {"review": review, "approval": approval}


def approve_review(
    output: Path, *, approved: bool, comment: str = "", reviewer: str = ""
) -> dict[str, object]:
    if not (Path(output) / "review.json").is_file():
        raise StateNotReadyError("This job has no review.json to approve.")
    payload = {
        "approved": bool(approved),
        "comment": comment,
        "reviewer": reviewer,
        "decided_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    target = Path(output) / REVIEW_APPROVAL
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def list_thumbnails(output: Path) -> dict[str, object]:
    directory = Path(output) / "thumbnails"
    files = sorted(path.name for path in directory.glob("*.png")) if directory.is_dir() else []
    choice = _read_json(Path(output) / THUMBNAIL_CHOICE)
    return {
        "variants": files,
        "selected": str(choice.get("selected") or (files[0] if files else "")),
    }


def select_thumbnail(output: Path, name: str) -> dict[str, object]:
    directory = Path(output) / "thumbnails"
    candidate = directory / name
    if not candidate.is_file() or candidate.parent != directory:
        raise StateNotReadyError(f"Unknown thumbnail variant: {name}")
    payload = {"selected": name}
    (Path(output) / THUMBNAIL_CHOICE).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return payload
