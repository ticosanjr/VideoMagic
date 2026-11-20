from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application import style_service
from videoflow.application.style_catalog import StyleCatalog
from videoflow.domain.errors import StyleError
from videoflow.domain.styles import StyleDefinition


def test_style_format_sets_aspect_and_safe_zones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    catalog = StyleCatalog(tmp_path / "styles")
    catalog.save(
        StyleDefinition(
            style_id="linked",
            name="Linked",
            format_id="vertical_9_16",
        )
    )
    stored = catalog.get("linked")
    assert stored.format_id == "vertical_9_16"
    assert stored.aspect_ratio == "9:16"
    assert stored.safe_zones["bottom_px"] == 380.0
    assert stored.caption_preset


def test_unknown_format_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    with pytest.raises(StyleError):
        style_service.save_style(
            style_id="bad-format",
            name="Bad",
            updates={"format_id": "does_not_exist"},
            catalog=StyleCatalog(tmp_path / "styles"),
        )
