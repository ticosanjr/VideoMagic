"""Public URL validation used by asset downloads and external fetches."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlparse

from videoflow.domain.errors import SearchBlockedError


def _is_private_host(host: str) -> bool:
    lowered = host.casefold().strip(".")
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(lowered)
        return address.is_private or address.is_loopback or address.is_link_local
    except ValueError:
        pass
    try:
        resolved = socket.getaddrinfo(lowered, None)
    except OSError:
        return False
    for item in resolved:
        try:
            address = ipaddress.ip_address(item[4][0])
        except (ValueError, IndexError):
            continue
        if address.is_private or address.is_loopback or address.is_link_local:
            return True
    return False


def _assert_public_url(url: str, allowed_hosts: Iterable[str] = ()) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SearchBlockedError(f"Unsupported URL: {url}")
    allowed = {item.casefold() for item in allowed_hosts if item.strip()}
    if parsed.hostname.casefold() in allowed:
        return
    if _is_private_host(parsed.hostname):
        raise SearchBlockedError(
            "Refusing to fetch a private or loopback host. Add it to "
            "allowed_external_hosts only if you trust it."
        )


def assert_public_url(url: str, allowed_hosts: Iterable[str] = ()) -> None:
    """Public wrapper for asset download URL checks."""

    _assert_public_url(url, allowed_hosts)


def url_allowed(url: str, allowed: Iterable[str]) -> bool:
    return url in set(allowed)
