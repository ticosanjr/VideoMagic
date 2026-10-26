"""Regression: missing local model files produce a domain error."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.models import install_model, installed_path, register_local_model
from videoflow.domain.errors import StateNotReadyError


def test_install_missing_local_model_is_actionable(tmp_path: Path) -> None:
    path = tmp_path / "local.bin"
    path.write_bytes(b"weights")
    register_local_model(
        model_id="mine",
        label="Mine",
        capability="tts",
        path=str(path),
    )
    assert installed_path("mine") == path

    path.unlink()

    with pytest.raises(StateNotReadyError, match="Local model is missing"):
        install_model("mine")
    assert installed_path("mine") is None
