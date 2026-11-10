"""Free/local research providers with citation-friendly caching.

Providers never invent content. They return normalized search results and
fetched documents; the LLM step must cite only URLs present in that manifest.
Network access is explicit: external providers call
``ensure_external_allowed`` and every fetched page is checked for private
hosts, size, and robots policy.
"""

from videoflow.application.search.cache import (
    _cache_path,
    _read_cache,
    _write_cache,
    cache_dir,
)
from videoflow.application.search.config import _search_config
from videoflow.application.search.documents import (
    _robots_allowed,
    _title_from_html,
    fetch_document,
    fetch_documents,
    html_text,
    source_manifest,
)
from videoflow.application.search.html import _TextParser
from videoflow.application.search.local import (
    _LOCAL_SUFFIXES,
    _local_search,
    _local_text,
    _snippet,
    _terms,
    local_url,
)
from videoflow.application.search.models import SearchDocument, SearchResult
from videoflow.application.search.urls import (
    _assert_public_url,
    _is_private_host,
    assert_public_url,
    url_allowed,
)
from videoflow.application.search.web import (
    _crawl_search,
    _internet_archive_search,
    _searxng_search,
    _wikipedia_search,
    search_web,
)
from videoflow.application.settings import SearchSettings
from videoflow.domain.errors import SearchBlockedError, SearchError

__all__ = [
    "_LOCAL_SUFFIXES",
    "_TextParser",
    "_assert_public_url",
    "_cache_path",
    "_crawl_search",
    "_internet_archive_search",
    "_is_private_host",
    "_local_search",
    "_local_text",
    "_read_cache",
    "_robots_allowed",
    "_search_config",
    "_searxng_search",
    "_snippet",
    "_terms",
    "_title_from_html",
    "_wikipedia_search",
    "_write_cache",
    "SearchBlockedError",
    "SearchError",
    "SearchDocument",
    "SearchResult",
    "SearchSettings",
    "assert_public_url",
    "cache_dir",
    "fetch_document",
    "fetch_documents",
    "html_text",
    "local_url",
    "search_web",
    "source_manifest",
    "url_allowed",
]
