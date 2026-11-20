from __future__ import annotations

import pytest
from scripts.acceptance_3_3 import (
    check_compositors,
    check_editorial,
    check_shorts,
)

pytestmark = pytest.mark.slow


def test_editorial_clean_acceptance() -> None:
    result = check_editorial()
    assert result["ok"] is True
    assert result["clipped_words"] == 0
    assert result["stutters_removed"] >= 1


def test_shorts_style_matrix_acceptance() -> None:
    result = check_shorts()
    assert result["ok"] is True
    assert len(result["styles"]) == 5
    assert any(item["aspect_ratio"] == "4:5" for item in result["styles"])


def test_compositor_surface_acceptance() -> None:
    result = check_compositors()
    assert result["ok"] is True
    assert result["tool_count"] == 35
