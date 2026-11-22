"""Search free and local asset providers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from videoflow.application.settings import AppSettings, load_settings
from videoflow.domain.errors import SearchError
from videoflow.domains.media.models import AssetCandidate

from .search_keyless import _internet_archive, _openverse, _wikimedia, _youtube
from .search_stock import _pexels, _pixabay

_HTML = re.compile(r"<[^>]+>")

PROVIDERS: dict[str, Any] = {
    "pexels": _pexels,
    "pixabay": _pixabay,
    "openverse": _openverse,
    "wikimedia": _wikimedia,
    "internet_archive": _internet_archive,
    "youtube": _youtube,
}


def search_assets(
    query: str,
    *,
    providers: Iterable[str],
    settings: AppSettings | None = None,
    media: str = "all",
    limit: int = 3,
    allow_external_services: bool = False,
    allowed_external_hosts: Iterable[str] = (),
) -> list[AssetCandidate]:
    current = settings or load_settings()
    results: list[AssetCandidate] = []
    errors: list[str] = []
    for name in providers:
        provider = name.strip().casefold()
        function = PROVIDERS.get(provider)
        if function is None:
            continue
        try:
            if provider in {"pixabay", "openverse"} or provider == "pexels":
                batch = function(
                    query,
                    settings=current,
                    limit=limit,
                    media=media,
                    allow_external_services=allow_external_services,
                    allowed_external_hosts=allowed_external_hosts,
                )
            else:
                batch = function(
                    query,
                    limit=limit,
                    media=media,
                    allow_external_services=allow_external_services,
                    allowed_external_hosts=allowed_external_hosts,
                )
            results.extend(batch)
        except Exception as exc:  # noqa: BLE001 - try the next provider
            errors.append(f"{provider}: {exc}")
    if not results and errors:
        raise SearchError("No asset provider returned results: " + " | ".join(errors))
    return results[:limit]
