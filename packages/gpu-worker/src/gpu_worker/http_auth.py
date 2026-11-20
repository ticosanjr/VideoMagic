"""Client classification and token helpers for the worker HTTP app."""

from __future__ import annotations

import ipaddress
from pathlib import Path


def is_private_client(host: str | None) -> bool:
    try:
        address = ipaddress.ip_address(str(host or ""))
    except ValueError:
        return False
    return bool(address.is_private or address.is_loopback)


def is_loopback_client(host: str | None) -> bool:
    try:
        return ipaddress.ip_address(str(host or "")).is_loopback
    except ValueError:
        return False


def matches_allowlist(host: str | None, entries: tuple[str, ...]) -> bool:
    if not entries:
        return False
    try:
        address = ipaddress.ip_address(str(host or ""))
    except ValueError:
        return False
    for entry in entries:
        try:
            if "/" in entry:
                if address in ipaddress.ip_network(entry, strict=False):
                    return True
            elif address == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def read_token_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


__all__ = [
    "is_loopback_client",
    "is_private_client",
    "matches_allowlist",
    "read_token_file",
]
