"""Local corpus search."""

from __future__ import annotations

import re
from pathlib import Path

from videoflow.application.search.models import SearchResult
from videoflow.application.settings import SearchSettings

_LOCAL_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm", ".json", ".csv", ".srt"}


def _local_text(path: Path, max_bytes: int) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        data = path.read_bytes()
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _snippet(text: str, terms: set[str], width: int = 280) -> str:
    lowered = text.casefold()
    for term in terms:
        index = lowered.find(term)
        if index >= 0:
            start = max(0, index - width // 3)
            return re.sub(r"\s+", " ", text[start : start + width]).strip()
    return re.sub(r"\s+", " ", text[:width]).strip()


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^0-9A-Za-zÀ-ÿ_]+", text.casefold())
        if len(token) > 2
    }


def _local_search(
    query: str, settings: SearchSettings, limit: int
) -> list[SearchResult]:
    terms = _terms(query)
    if not terms:
        return []
    results: list[SearchResult] = []
    roots = [Path(item).expanduser() for item in settings.local_paths if item.strip()]
    for root in roots:
        candidates = (
            [root]
            if root.is_file()
            else sorted(root.rglob("*"))
            if root.is_dir()
            else []
        )
        for path in candidates[:5000]:
            if len(results) >= limit or not path.is_file():
                continue
            if path.suffix.casefold() not in _LOCAL_SUFFIXES:
                continue
            text = _local_text(path, settings.max_bytes)
            if not text:
                continue
            score = sum(1 for term in terms if term in text.casefold())
            if score == 0:
                continue
            title = path.stem
            results.append(
                SearchResult(
                    title=title,
                    url=path.resolve().as_uri(),
                    snippet=_snippet(text, terms),
                    provider="local",
                )
            )
    results.sort(key=lambda item: item.title.casefold())
    return results[:limit]


def local_url(path: Path) -> str:
    return Path(path).expanduser().resolve().as_uri()
