"""Normalized search results and fetched documents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    provider: str = "local"
    published_at: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "provider": self.provider,
            "published_at": self.published_at,
        }


@dataclass(frozen=True, slots=True)
class SearchDocument:
    url: str
    title: str
    text: str
    provider: str = "web"
    fetched_at: str = ""
    sha256: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "provider": self.provider,
            "fetched_at": self.fetched_at,
            "sha256": self.sha256,
        }
