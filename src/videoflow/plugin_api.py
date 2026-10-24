"""Public registration surface for local plugins.

A plugin imports this module and registers an exporter or a provider. The core
calls the same registries, so a plugin adds capability without editing core
modules.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

EXPORTERS: dict[str, Callable[..., Any]] = {}
PROVIDERS: dict[str, dict[str, Any]] = {}
PANELS: dict[str, dict[str, str]] = {}


def register_exporter(name: str, handler: Callable[..., Any]) -> None:
    """Register a writer called when an export target uses this name."""

    if not name or not callable(handler):
        raise ValueError("register_exporter needs a name and a callable")
    EXPORTERS[name] = handler


def register_provider(capability: str, config: dict[str, Any]) -> None:
    """Register a fallback provider for a capability."""

    if not capability:
        raise ValueError("register_provider needs a capability")
    PROVIDERS[capability] = dict(config)


def register_panel(panel_id: str, *, title: str, url: str) -> None:
    """Declare a read-only panel URL served outside this process."""

    if not panel_id or not url:
        raise ValueError("register_panel needs an id and a url")
    PANELS[panel_id] = {"title": title or panel_id, "url": url}


def exporter(name: str) -> Callable[..., Any] | None:
    return EXPORTERS.get(name)


def provider(capability: str) -> dict[str, Any] | None:
    return PROVIDERS.get(capability)


def reset() -> None:
    """Clear registrations (tests and hot reload)."""

    EXPORTERS.clear()
    PROVIDERS.clear()
    PANELS.clear()
