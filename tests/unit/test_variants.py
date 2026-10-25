from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.variants import compare_variants, select_variant


def test_compare_variants_and_select_winner(tmp_path: Path) -> None:
    output = tmp_path / "out"
    (output / "thumbnails").mkdir(parents=True)
    (output / "thumbnails" / "a.png").write_bytes(b"x")
    (output / "thumbnails" / "b.png").write_bytes(b"x")
    (output / "review").mkdir()
    (output / "thumbnail_metrics.json").write_text(
        json.dumps({"a.png": {"impressions": 100, "clicks": 9}}),
        encoding="utf-8",
    )
    result = {
        "variants": [
            {
                "name": "one",
                "output": str(output / "one"),
                "summary": {"shorts": [{"score": 85.0}], "artifacts": {"mp4": "x"}},
            },
            {"name": "two", "output": str(output / "two"), "summary": {"shorts": []}},
        ],
        "shorts": [
            {"title": "Hook A", "score": 91.0, "duration_sec": 42.0, "path": "a.mp4"},
            {"title": "Hook B", "score": 77.0, "duration_sec": 58.0, "path": "b.mp4"},
        ],
    }
    payload = compare_variants(output, result)
    assert payload["count"] == 4
    assert payload["items"][0]["metrics"]["best_score"] == 85.0
    assert [thumb["name"] for thumb in payload["thumbnails"]] == ["a.png", "b.png"]
    assert payload["thumbnails"][0]["metrics"]["clicks"] == 9

    select_variant(output, "short-1")
    assert compare_variants(output, result)["winner"] == "short-1"
