"""Shared text normalization and token helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable

_TOKEN = re.compile(r"[a-z0-9à-ÿ]+")


def normalize_text(text: str) -> str:
    return " ".join(text.casefold().split()).strip(" .,!?;:\"'")


def token_list(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


def token_set(text: str, *, min_length: int = 3) -> set[str]:
    return {
        token
        for token in token_list(text)
        if len(token) >= min_length or token.isdigit()
    }


def content_tokens(text: str, stopwords: Iterable[str]) -> set[str]:
    blocked = set(stopwords)
    return {
        token
        for token in token_set(text)
        if len(token) >= 4 and token not in blocked
    }
