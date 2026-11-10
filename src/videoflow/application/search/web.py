"""Web search providers and provider orchestration."""

from __future__ import annotations

import logging
from collections.abc import Iterable

import httpx

from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.search.config import _search_config
from videoflow.application.search.documents import fetch_document
from videoflow.application.search.html import _TAG
from videoflow.application.search.local import _local_search, _snippet, _terms
from videoflow.application.search.models import SearchResult
from videoflow.application.settings import AppSettings, SearchSettings
from videoflow.domain.errors import SearchError

logger = logging.getLogger(__name__)


def _searxng_search(
    query: str,
    settings: SearchSettings,
    limit: int,
    *,
    allow_external_services: bool,
    allowed_external_hosts: tuple[str, ...],
) -> list[SearchResult]:
    base = settings.searxng_url.strip().rstrip("/")
    if not base:
        raise SearchError("SearXNG URL is not configured.")
    ensure_external_allowed(
        base,
        capability="web_search",
        allow_external_services=allow_external_services,
        allowed_hosts=allowed_external_hosts,
    )
    response = httpx.get(
        f"{base}/search",
        params={"q": query, "format": "json", "language": "auto"},
        timeout=settings.timeout_seconds,
        headers={"User-Agent": "VideoFlowResearch/1.0"},
    )
    if response.status_code >= 400:
        raise SearchError(f"SearXNG returned HTTP {response.status_code}.")
    payload = response.json()
    results = []
    for item in payload.get("results", [])[:limit]:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        results.append(
            SearchResult(
                title=str(item.get("title") or item["url"]),
                url=str(item["url"]),
                snippet=str(item.get("content") or item.get("snippet") or ""),
                provider="searxng",
            )
        )
    return results


def _wikipedia_search(
    query: str,
    settings: SearchSettings,
    limit: int,
    *,
    allow_external_services: bool,
    allowed_external_hosts: tuple[str, ...],
) -> list[SearchResult]:
    base = f"https://{settings.wikipedia_language}.wikipedia.org"
    ensure_external_allowed(
        base,
        capability="web_search",
        allow_external_services=allow_external_services,
        allowed_hosts=allowed_external_hosts,
    )
    response = httpx.get(
        f"{base}/w/api.php",
        params={
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": limit,
        },
        timeout=settings.timeout_seconds,
        headers={"User-Agent": "VideoFlowResearch/1.0"},
    )
    if response.status_code >= 400:
        raise SearchError(f"Wikipedia returned HTTP {response.status_code}.")
    payload = response.json()
    results = []
    for item in (payload.get("query") or {}).get("search", [])[:limit]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        title = str(item["title"])
        results.append(
            SearchResult(
                title=title,
                url=f"{base}/wiki/{title.replace(' ', '_')}",
                snippet=_TAG.sub(" ", str(item.get("snippet") or "")).strip(),
                provider="wikipedia",
                published_at=str(item.get("timestamp") or ""),
            )
        )
    return results


def _internet_archive_search(
    query: str,
    settings: SearchSettings,
    limit: int,
    *,
    allow_external_services: bool,
    allowed_external_hosts: tuple[str, ...],
) -> list[SearchResult]:
    base = "https://archive.org"
    ensure_external_allowed(
        base,
        capability="web_search",
        allow_external_services=allow_external_services,
        allowed_hosts=allowed_external_hosts,
    )
    response = httpx.get(
        f"{base}/advancedsearch.php",
        params={
            "q": query,
            "fl[]": ["identifier", "title", "date", "description"],
            "rows": limit,
            "page": 1,
            "output": "json",
        },
        timeout=settings.timeout_seconds,
        headers={"User-Agent": "VideoFlowResearch/1.0"},
    )
    if response.status_code >= 400:
        raise SearchError(f"Internet Archive returned HTTP {response.status_code}.")
    payload = response.json()
    results = []
    for item in (payload.get("response") or {}).get("docs", [])[:limit]:
        if not isinstance(item, dict) or not item.get("identifier"):
            continue
        identifier = str(item["identifier"])
        results.append(
            SearchResult(
                title=str(item.get("title") or identifier),
                url=f"{base}/details/{identifier}",
                snippet=str(item.get("description") or "")[:400],
                provider="internet_archive",
                published_at=str(item.get("date") or ""),
            )
        )
    return results


def _crawl_search(
    query: str,
    settings: SearchSettings,
    limit: int,
    *,
    allow_external_services: bool,
    allowed_external_hosts: tuple[str, ...],
) -> list[SearchResult]:
    terms = _terms(query)
    results: list[SearchResult] = []
    for seed in settings.seed_urls:
        if len(results) >= limit:
            break
        seed = seed.strip()
        if not seed:
            continue
        try:
            document = fetch_document(
                seed,
                settings,
                allow_external_services=allow_external_services,
                allowed_external_hosts=allowed_external_hosts,
            )
        except Exception as exc:  # noqa: BLE001 - one seed must not stop the crawl
            logger.warning("crawl seed %s failed: %s", seed, exc)
            continue
        if not any(term in document.text.casefold() for term in terms):
            continue
        results.append(
            SearchResult(
                title=document.title or seed,
                url=document.url,
                snippet=_snippet(document.text, terms),
                provider="crawl",
            )
        )
    return results[:limit]


def search_web(
    query: str,
    *,
    settings: AppSettings | SearchSettings | None = None,
    providers: Iterable[str] | None = None,
    allow_external_services: bool = False,
    allowed_external_hosts: Iterable[str] = (),
    limit: int | None = None,
) -> list[SearchResult]:
    config = _search_config(settings)
    if not config.enabled:
        raise SearchError("Web search is disabled in Settings.")
    names = [
        item.strip().casefold()
        for item in (providers or config.providers)
        if item.strip()
    ]
    maximum = limit or config.max_results
    hosts = tuple(allowed_external_hosts)
    results: list[SearchResult] = []
    seen: set[str] = set()
    errors: list[str] = []
    for name in names:
        try:
            if name == "local":
                batch = _local_search(query, config, maximum)
            elif name == "crawl":
                batch = _crawl_search(
                    query,
                    config,
                    maximum,
                    allow_external_services=allow_external_services,
                    allowed_external_hosts=hosts,
                )
            elif name == "searxng":
                batch = _searxng_search(
                    query,
                    config,
                    maximum,
                    allow_external_services=allow_external_services,
                    allowed_external_hosts=hosts,
                )
            elif name == "wikipedia":
                batch = _wikipedia_search(
                    query,
                    config,
                    maximum,
                    allow_external_services=allow_external_services,
                    allowed_external_hosts=hosts,
                )
            elif name == "internet_archive":
                batch = _internet_archive_search(
                    query,
                    config,
                    maximum,
                    allow_external_services=allow_external_services,
                    allowed_external_hosts=hosts,
                )
            else:
                raise SearchError(f"Unknown search provider: {name}")
        except Exception as exc:  # noqa: BLE001 - try the next provider
            errors.append(f"{name}: {exc}")
            logger.info("search provider %s failed: %s", name, exc)
            continue
        for result in batch:
            if result.url in seen:
                continue
            seen.add(result.url)
            results.append(result)
            if len(results) >= maximum:
                return results
    if not results and errors:
        raise SearchError("No search provider returned results: " + " | ".join(errors))
    return results
