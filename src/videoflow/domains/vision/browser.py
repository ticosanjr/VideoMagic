"""Locate a Chromium binary for HTML captures."""

from __future__ import annotations

from . import commands
from .errors import MissingCommandError


def _chrome() -> str:
    browser = commands.resolve_binary(
        "google-chrome",
        "chromium",
        "chromium-browser",
        "chrome",
        env="VF_CHROME_BIN",
    )
    if browser is None:
        raise MissingCommandError(
            "Chrome/Chromium is required for html motion graphics",
            details={"env": ["VF_CHROME_BIN"], "capability": "html"},
        )
    return browser
