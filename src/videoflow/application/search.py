"""Free/local research providers with citation-friendly caching.

Providers never invent content. They return normalized search results and
fetched documents; the LLM step must cite only URLs present in that manifest.
Network access is explicit: external providers call
``ensure_external_allowed`` and every fetched page is checked for private
hosts, size, and robots policy.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import socket
import time
import urllib.robotparser
from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from videoflow.application.capabilities import ensure_external_allowed
from videoflow.application.settings import AppSettings, SearchSettings, load_settings
from videoflow.domain.errors import SearchBlockedError, SearchError
from videoflow.runtime import portable_home

logger = logging.getLogger(__name__)

_LOCAL_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm", ".json", ".csv", ".srt"}
_TAG = re.compile(r"<[^>]+>")


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


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
        else:
            self.parts.append(text)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.parts)).strip()


def cache_dir() -> Path:
    directory = portable_home() / "search-cache"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _cache_path(url: str) -> Path:
    return cache_dir() / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]}.json"


def _read_cache(url: str, ttl_hours: int) -> dict[str, Any] | None:
    try:
        payload = json.loads(_cache_path(url).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    fetched = float(payload.get("fetched_ts") or 0)
    if time.time() - fetched > ttl_hours * 3600:
        return None
    return payload


def _write_cache(url: str, payload: dict[str, Any]) -> None:
    target = _cache_path(url)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(target)


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


def _robots_allowed(url: str, *, timeout: float) -> bool:
    parsed = urlparse(url)
    robots = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = httpx.get(robots, timeout=timeout)
    except httpx.HTTPError:
        return True
    if response.status_code >= 400:
        return True
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch("VideoFlowResearch/1.0", url)


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


def _local_search(query: str, settings: SearchSettings, limit: int) -> list[SearchResult]:
    terms = _terms(query)
    if not terms:
        return []
    results: list[SearchResult] = []
    roots = [Path(item).expanduser() for item in settings.local_paths if item.strip()]
    for root in roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*")) if root.is_dir() else []
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


def _search_config(settings: AppSettings | SearchSettings | None) -> SearchSettings:
    if isinstance(settings, AppSettings):
        return settings.search
    if isinstance(settings, SearchSettings):
        return settings
    return load_settings().search


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
    names = [item.strip().casefold() for item in (providers or config.providers) if item.strip()]
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


def _title_from_html(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", _TAG.sub(" ", match.group(1))).strip() if match else ""


def html_text(html: str) -> tuple[str, str]:
    parser = _TextParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - malformed HTML
        return _title_from_html(html), _TAG.sub(" ", html)
    return parser.title or _title_from_html(html), parser.text()


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
        title, text = html_text(body.decode(response.encoding or "utf-8", errors="replace"))
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
            logger.info("fetch failed for %s: %s", result.url, exc)
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


def url_allowed(url: str, allowed: Iterable[str]) -> bool:
    return url in set(allowed)


def local_url(path: Path) -> str:
    return Path(path).expanduser().resolve().as_uri()
