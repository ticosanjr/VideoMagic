"""Redact secret material before it can reach a log, a comment, or an MCP resource."""

from __future__ import annotations

from collections.abc import Iterable


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace each non-empty secret with ``[REDACTED]``.

    Callers must pass the real secret values, not names. Empty strings are
    ignored so a missing key cannot wipe the text.
    """

    redacted = text
    for secret in secrets:
        if not secret:
            continue
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted
