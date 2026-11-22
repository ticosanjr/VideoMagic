"""Shared provider authorization helper."""

from __future__ import annotations

import re
from collections.abc import Iterable

from videoflow.application.capabilities import ensure_external_allowed

_HTML = re.compile(r"<[^>]+>")

def _check_provider(
    url: str,
    *,
    allow_external_services: bool,
    allowed_external_hosts: Iterable[str],
) -> None:
    ensure_external_allowed(
        url,
        capability="stock_assets",
        allow_external_services=allow_external_services,
        allowed_hosts=tuple(allowed_external_hosts),
    )


