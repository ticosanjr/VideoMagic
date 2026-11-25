"""Locate a Chromium binary for HTML captures."""

from __future__ import annotations

import os
from pathlib import Path

from ..toolkit import commands
from ..toolkit.errors import MissingCommandError


def _is_windows() -> bool:
    return os.name == "nt"


def _env_path(name: str, default: str) -> Path:
    value = os.environ.get(name) or os.environ.get(name.title()) or default
    return Path(value).expanduser()


def _windows_candidates() -> list[Path]:
    """Standard Edge/Chrome and Playwright Chromium locations on Windows."""

    if not _is_windows():
        return []
    program_files = _env_path("PROGRAMFILES", r"C:\Program Files")
    program_files_x86 = _env_path("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    local_app = _env_path("LOCALAPPDATA", r"%LOCALAPPDATA%")
    candidates = [
        program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        program_files / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local_app / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    playwright = local_app / "ms-playwright"
    if playwright.is_dir():
        for pattern in (
            "chromium-*/chrome-win/chrome.exe",
            "chromium-*/chrome-win64/chrome.exe",
            "chromium_headless_shell-*/chrome-win/headless_shell.exe",
            "chromium-*/chrome-linux/chrome",
        ):
            candidates.extend(sorted(playwright.glob(pattern), reverse=True))
    return candidates


def _chrome() -> str:
    browser = commands.resolve_binary(
        "google-chrome",
        "chromium",
        "chromium-browser",
        "chrome",
        env="VF_CHROME_BIN",
    )
    if browser is None:
        for candidate in _windows_candidates():
            try:
                if candidate.is_file():
                    return str(candidate)
            except OSError:
                continue
    if browser is None:
        raise MissingCommandError(
            "Chrome/Chromium is required for html motion graphics",
            details={"env": ["VF_CHROME_BIN"], "capability": "html"},
        )
    return browser


__all__ = ["_chrome"]
