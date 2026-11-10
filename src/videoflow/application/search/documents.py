"""Fetch and normalize web or local documents."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.search.cache import _read_cache, _write_cache
from videoflow.application.search.config import _search_config
from videoflow.application.search.html import _title_from_html, html_text
from videoflow.application.search.local import _local_text
from videoflow.application.search.models import SearchDocument, SearchResult
from videoflow.application.search.urls import _assert_public_url
from videoflow.application.settings import AppSettings, SearchSettings
from videoflow.domain.errors import SearchBlockedError, SearchError


def _robots_allowed(url: str, *, timeout: float) -> bool:
    parsed = urlparse(url)
    robots = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = httpx.get(robots, timeout=timeout)
    except httpx.HTTPError:
        return True
    if response.status_code >= 400:
        return True
    import urllib.robotparser

    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch("VideoFlowResearch/1.0", url)


def fetch_document(
    url: str,
    settings: SearchSettings | AppSettings | None = None,
    *,
    allow_external_services: bool = False,
    allowed_external_hosts: Iterable[str] = (),
) -> SearchDocument:
    config = _search_config(settings)
    if url.startswith("file://"):
        path = Path(unquote(urlparse(url).path))
        text = _local_text(path, config.max_bytes)
        return SearchDocument(
            url=url,
            title=path.stem,
            text=text,
            provider="local",
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SearchError(f"Unsupported fetch URL: {url}")
    _assert_public_url(url, allowed_external_hosts)
    ensure_external_allowed(
        url,
        capability="web_search",
        allow_external_services=allow_external_services,
        allowed_hosts=tuple(allowed_external_hosts),
    )
    cached = _read_cache(url, config.cache_ttl_hours)
    if cached is not None:
        return SearchDocument(
            url=url,
            title=str(cached.get("title") or url),
            text=str(cached.get("text") or ""),
            provider="cache",
            fetched_at=str(cached.get("fetched_at") or ""),
            sha256=str(cached.get("sha256") or ""),
        )
    if not _robots_allowed(url, timeout=config.timeout_seconds):
        raise SearchBlockedError(f"robots.txt disallows fetching {url}")
    response = httpx.get(
        url,
        timeout=config.timeout_seconds,
        headers={"User-Agent": "VideoFlowResearch/1.0"},
        follow_redirects=True,
    )
    if response.status_code >= 400:
        raise SearchError(f"Fetch returned HTTP {response.status_code}: {url}")
    content_type = response.headers.get("content-type", "").casefold()
    body = response.content[: config.max_bytes]
    if "html" in content_type or b"<html" in body[:500].lower():
        title, text = html_text(
            body.decode(response.encoding or "utf-8", errors="replace")
        )
    elif any(kind in content_type for kind in ("text/", "json", "xml")):
        text = body.decode(response.encoding or "utf-8", errors="replace")
        title = _title_from_html(text) or url
    else:
        raise SearchError(f"Unsupported content type: {content_type or 'unknown'}")
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    document = SearchDocument(
        url=url,
        title=title or url,
        text=text,
        provider=parsed.hostname or "web",
        fetched_at=fetched_at,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    _write_cache(
        url,
        {
            "title": document.title,
            "text": document.text,
            "fetched_at": fetched_at,
            "fetched_ts": time.time(),
            "sha256": document.sha256,
        },
    )
    return document


def fetch_documents(
    results: Iterable[SearchResult],
    settings: SearchSettings | AppSettings | None = None,
    *,
    limit: int = 3,
    allow_external_services: bool = False,
    allowed_external_hosts: Iterable[str] = (),
) -> list[SearchDocument]:
    documents: list[SearchDocument] = []
    for result in results:
        if len(documents) >= limit:
            break
        try:
            documents.append(
                fetch_document(
                    result.url,
                    settings,
                    allow_external_services=allow_external_services,
                    allowed_external_hosts=allowed_external_hosts,
                )
            )
        except Exception as exc:  # noqa: BLE001 - a bad page must not stop research
            import logging

            logging.getLogger(__name__).info(
                "fetch failed for %s: %s", result.url, exc
            )
    return documents


def source_manifest(
    results: Iterable[SearchResult],
    documents: Iterable[SearchDocument] = (),
) -> list[dict[str, Any]]:
    fetched = {document.url: document for document in documents}
    manifest = []
    for result in results:
        document = fetched.get(result.url)
        manifest.append(
            {
                **result.to_dict(),
                "fetched": document is not None,
                "sha256": document.sha256 if document is not None else "",
                "text_chars": len(document.text) if document is not None else 0,
            }
        )
    return manifest
