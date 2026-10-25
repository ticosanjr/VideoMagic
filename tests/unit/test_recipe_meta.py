from __future__ import annotations

import json
from pathlib import Path

from videoflow.application import recipe_meta


def test_favorites_recent_and_default_recut(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    assert recipe_meta.get_meta("recut_replacement").favorite is True
    assert recipe_meta.get_meta("recut_replacement_retakes").favorite is True
    assert recipe_meta.get_meta("youtube_talking_head").favorite is False

    recipe_meta.set_favorite("youtube_talking_head", True)
    assert recipe_meta.get_meta("youtube_talking_head").favorite is True
    recipe_meta.set_favorite("recut_replacement", False)
    assert recipe_meta.get_meta("recut_replacement").favorite is False

    recipe_meta.touch("youtube_talking_head")
    recipe_meta.touch("youtube_talking_head")
    recipe_meta.touch("viral_shorts_batch")
    meta = recipe_meta.get_meta("youtube_talking_head")
    assert meta.use_count == 2
    assert meta.last_used_at

    payload = json.loads((tmp_path / "recipe_meta.json").read_text())
    assert payload["youtube_talking_head"]["favorite"] is True

    recipe_meta.set_tags("youtube_talking_head", ["interview", "long"])
    assert recipe_meta.get_meta("youtube_talking_head").tags == ["interview", "long"]


def test_recent_recipes_are_ordered_by_last_use(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    recipe_meta.touch("viral_shorts_batch", at="2026-01-01T10:00:00+00:00")
    recipe_meta.touch("youtube_talking_head", at="2026-01-02T10:00:00+00:00")
    recent = recipe_meta.recent(["viral_shorts_batch", "youtube_talking_head"], limit=1)
    assert recent == ["youtube_talking_head"]
