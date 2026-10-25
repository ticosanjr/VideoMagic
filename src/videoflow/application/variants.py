"""Side-by-side comparison and winner selection for recipe variants and Shorts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from videoflow.application.deliverables import list_thumbnails, thumbnail_metrics
from videoflow.domain.errors import StateNotReadyError

WINNER_FILE = "review/variant_winner.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _short_entry(index: int, short: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"short-{index + 1}",
        "kind": "short",
        "name": str(short.get("title") or f"Short {index + 1}"),
        "duration_sec": short.get("duration_sec") or short.get("duration"),
        "score": short.get("score"),
        "hook": short.get("hook") or short.get("title"),
        "path": short.get("path"),
        "metrics": {
            "score": short.get("score"),
            "duration_sec": short.get("duration_sec") or short.get("duration"),
        },
    }


def compare_variants(output: Path, result: dict[str, Any] | None) -> dict[str, Any]:
    output = Path(output)
    result = result or {}
    items: list[dict[str, Any]] = []
    for index, variant in enumerate(result.get("variants") or []):
        if not isinstance(variant, dict):
            continue
        summary = variant.get("summary") if isinstance(variant.get("summary"), dict) else {}
        shorts = summary.get("shorts") if isinstance(summary.get("shorts"), list) else []
        best = max(
            (float(item.get("score") or 0.0) for item in shorts if isinstance(item, dict)),
            default=0.0,
        )
        items.append(
            {
                "id": f"variant-{index + 1}",
                "kind": "variant",
                "name": str(variant.get("name") or f"Variant {index + 1}"),
                "path": variant.get("output"),
                "shorts": len(shorts),
                "metrics": {
                    "best_score": round(best, 2),
                    "shorts": len(shorts),
                    "artifacts": len(summary.get("artifacts") or {}),
                },
            }
        )
    for index, short in enumerate(result.get("shorts") or []):
        if isinstance(short, dict):
            items.append(_short_entry(index, short))

    thumbnails = list_thumbnails(output)
    metrics = {str(item.get("name")): item for item in thumbnail_metrics(output)}
    thumbs = [
        {
            "name": name,
            "metrics": metrics.get(name, {}),
        }
        for name in thumbnails.get("variants", [])
    ]
    winner = _read(output / WINNER_FILE).get("selected", "")
    return {
        "ok": True,
        "items": items,
        "thumbnails": thumbs,
        "winner": winner,
        "count": len(items),
    }


def select_variant(output: Path, name: str) -> dict[str, Any]:
    output = Path(output)
    if not name.strip():
        raise StateNotReadyError("Choose a variant to mark as the winner.")
    payload = {"selected": name.strip()}
    path = output / WINNER_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
