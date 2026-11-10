from __future__ import annotations

import socket
from pathlib import Path

import pytest

from videoflow.application import search
from videoflow.application.search import cache, config, documents, html, local, urls, web
from videoflow.application.settings import AppSettings, SearchSettings
from videoflow.domain.errors import SearchBlockedError, SearchError


def test_private_host_detection(monkeypatch) -> None:
    assert urls._is_private_host("localhost")
    assert urls._is_private_host("printer.local")
    assert urls._is_private_host("127.0.0.1")
    assert urls._is_private_host("10.0.0.1")
    assert urls._is_private_host("169.254.1.1")
    assert not urls._is_private_host("8.8.8.8")

    monkeypatch.setattr(
        urls.socket,
        "getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 0))],
    )
    assert urls._is_private_host("internal.example")

    monkeypatch.setattr(
        urls.socket,
        "getaddrinfo",
        lambda host, port: (_ for _ in ()).throw(OSError("dns")),
    )
    assert not urls._is_private_host("missing.example")


def test_assert_public_url_branches() -> None:
    with pytest.raises(SearchBlockedError, match="Unsupported URL"):
        urls._assert_public_url("ftp://example.com")
    with pytest.raises(SearchBlockedError, match="Unsupported URL"):
        urls._assert_public_url("https:///path")
    urls._assert_public_url("http://127.0.0.1", ["127.0.0.1"])
    with pytest.raises(SearchBlockedError, match="private or loopback"):
        urls._assert_public_url("http://127.0.0.1")
    urls.assert_public_url("https://8.8.8.8")
    assert urls.url_allowed("https://a", ["https://a", "https://b"])
    assert not urls.url_allowed("https://c", ["https://a"])


def test_cache_round_trip_and_invalid_payloads(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    cache._write_cache("https://example.com/a", {"fetched_ts": 1_700_000_000, "text": "x"})
    assert cache._read_cache("https://example.com/a", 999_999)["text"] == "x"
    assert cache._read_cache("https://example.com/a", 0) is None

    path = cache._cache_path("https://example.com/b")
    path.write_text("not json", encoding="utf-8")
    assert cache._read_cache("https://example.com/b", 24) is None
    path.write_text("[]", encoding="utf-8")
    assert cache._read_cache("https://example.com/b", 24) is None


def test_local_helpers_and_search(tmp_path: Path) -> None:
    assert local._local_text(tmp_path / "missing.txt", 10) == ""
    big = tmp_path / "big.txt"
    big.write_text("x" * 100, encoding="utf-8")
    assert local._local_text(big, 10) == ""
    assert local._snippet("alpha beta gamma", {"gamma"})
    assert local._snippet("alpha beta", {"missing"}) == "alpha beta"
    assert local._terms("ab cd court") == {"court"}
    assert local._local_search("court", SearchSettings(local_paths=[]), 5) == []
    assert local._local_search(
        "court", SearchSettings(local_paths=[str(tmp_path / "missing")]), 5
    ) == []

    root = tmp_path / "corpus"
    root.mkdir()
    (root / "one.md").write_text("court record", encoding="utf-8")
    (root / "two.bin").write_text("court record", encoding="utf-8")
    results = local._local_search("court", SearchSettings(local_paths=[str(root)]), 5)
    assert len(results) == 1
    single = local._local_search("court", SearchSettings(local_paths=[str(root / "one.md")]), 5)
    assert len(single) == 1
    assert local.local_url(root / "one.md").startswith("file://")


def test_html_helpers(monkeypatch) -> None:
    assert html._title_from_html("<p>no title</p>") == ""
    assert html.html_text("<html><body><p>Text</p></body></html>")[1] == "Text"
    assert html.html_text("<title>Only</title>")[0] == "Only"

    class Broken(html._TextParser):
        def feed(self, data: str) -> None:
            raise ValueError("bad")

    monkeypatch.setattr(html, "_TextParser", Broken)
    title, text = html.html_text("<title>T</title><p>Body</p>")
    assert title == "T"
    assert "Body" in text


class _Response:
    def __init__(self, status_code=200, headers=None, content=b"", text="", payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content
        self.text = text
        self.encoding = "utf-8"
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_fetch_document_file_and_errors(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "note.md"
    path.write_text("local evidence", encoding="utf-8")
    document = documents.fetch_document(path.as_uri(), SearchSettings())
    assert document.text == "local evidence"
    assert document.provider == "local"

    with pytest.raises(SearchError, match="Unsupported fetch URL"):
        documents.fetch_document("ftp://example.com/a", SearchSettings())

    monkeypatch.setattr(documents, "_assert_public_url", lambda *a, **k: None)
    monkeypatch.setattr(documents, "_robots_allowed", lambda *a, **k: True)
    monkeypatch.setattr(documents, "_read_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        documents.httpx,
        "get",
        lambda *a, **k: _Response(500, {"content-type": "text/html"}),
    )
    with pytest.raises(SearchError, match="HTTP 500"):
        documents.fetch_document(
        "https://example.com/a", SearchSettings(), allow_external_services=True
    )

    monkeypatch.setattr(
        documents.httpx,
        "get",
        lambda *a, **k: _Response(
            200, {"content-type": "application/octet-stream"}, b"binary"
        ),
    )
    with pytest.raises(SearchError, match="Unsupported content type"):
        documents.fetch_document(
        "https://example.com/a", SearchSettings(), allow_external_services=True
    )

    monkeypatch.setattr(
        documents.httpx,
        "get",
        lambda *a, **k: _Response(
            200, {"content-type": "application/json"}, b'{"ok": true}'
        ),
    )
    assert documents.fetch_document(
        "https://example.com/a", SearchSettings(), allow_external_services=True
    ).text


def test_fetch_document_cache_and_fetch_documents(monkeypatch) -> None:
    monkeypatch.setattr(documents, "_assert_public_url", lambda *a, **k: None)
    monkeypatch.setattr(
        documents,
        "_read_cache",
        lambda *a, **k: {"title": "Cached", "text": "body", "fetched_at": "now", "sha256": "x"},
    )
    cached = documents.fetch_document(
        "https://example.com/a", SearchSettings(), allow_external_services=True
    )
    assert cached.provider == "cache"
    assert cached.title == "Cached"

    results = [
        search.SearchResult("a", "https://example.com/a"),
        search.SearchResult("b", "https://example.com/b"),
    ]
    monkeypatch.setattr(documents, "_read_cache", lambda *a, **k: None)
    monkeypatch.setattr(documents, "_robots_allowed", lambda *a, **k: True)
    monkeypatch.setattr(
        documents.httpx,
        "get",
        lambda *a, **k: _Response(200, {"content-type": "text/plain"}, b"body"),
    )
    fetched = documents.fetch_documents(
        results, SearchSettings(), limit=1, allow_external_services=True
    )
    assert len(fetched) == 1

    monkeypatch.setattr(
        documents,
        "fetch_document",
        lambda *a, **k: (_ for _ in ()).throw(OSError("bad")),
    )
    assert documents.fetch_documents(
        results, SearchSettings(), allow_external_services=True
    ) == []


def test_source_manifest_with_and_without_documents() -> None:
    results = [
        search.SearchResult("a", "https://example.com/a"),
        search.SearchResult("b", "https://example.com/b"),
    ]
    document = search.SearchDocument(url="https://example.com/a", title="a", text="body")
    manifest = documents.source_manifest(results, [document])
    assert manifest[0]["fetched"] is True
    assert manifest[1]["fetched"] is False


def test_search_config_branches(monkeypatch) -> None:
    settings = AppSettings()
    assert config._search_config(settings) is settings.search
    assert config._search_config(settings.search) is settings.search
    monkeypatch.setattr(config, "load_settings", lambda: settings)
    assert config._search_config(None) is settings.search


def test_web_provider_errors(monkeypatch) -> None:
    with pytest.raises(SearchError, match="disabled"):
        web.search_web("x", settings=SearchSettings(enabled=False))

    settings = SearchSettings(providers=["searxng"], searxng_url="")
    with pytest.raises(SearchError, match="No search provider"):
        web.search_web("x", settings=settings)

    monkeypatch.setattr(
        web.httpx, "get", lambda *a, **k: _Response(500)
    )
    with pytest.raises(SearchError, match="No search provider"):
        web.search_web(
            "x",
            settings=SearchSettings(providers=["wikipedia"]),
            allow_external_services=True,
        )
    with pytest.raises(SearchError, match="No search provider"):
        web.search_web(
            "x",
            settings=SearchSettings(providers=["internet_archive"]),
            allow_external_services=True,
        )


def test_web_provider_skips_bad_items(monkeypatch) -> None:
    monkeypatch.setattr(
        web.httpx,
        "get",
        lambda *a, **k: _Response(
            200,
            payload={
                "results": ["bad", {"url": ""}, {"url": "https://a", "title": "A"}],
            },
        ),
    )
    results = web.search_web(
        "x",
        settings=SearchSettings(providers=["searxng"], searxng_url="http://127.0.0.1:9"),
        allow_external_services=True,
    )
    assert len(results) == 1

    monkeypatch.setattr(
        web.httpx,
        "get",
        lambda *a, **k: _Response(
            200, payload={"query": {"search": ["bad", {"title": "T"}]}}
        ),
    )
    wiki = web.search_web(
        "x",
        settings=SearchSettings(providers=["wikipedia"]),
        allow_external_services=True,
    )
    assert wiki[0].url.endswith("/wiki/T")

    monkeypatch.setattr(
        web.httpx,
        "get",
        lambda *a, **k: _Response(
            200, payload={"response": {"docs": ["bad", {"identifier": "ia"}]}}
        ),
    )
    archive = web.search_web(
        "x",
        settings=SearchSettings(providers=["internet_archive"]),
        allow_external_services=True,
    )
    assert archive[0].url.endswith("/details/ia")


def test_crawl_search_errors_and_misses(monkeypatch) -> None:
    monkeypatch.setattr(
        web,
        "fetch_document",
        lambda *a, **k: (_ for _ in ()).throw(OSError("bad")),
    )
    assert web._crawl_search(
        "x",
        SearchSettings(seed_urls=["https://example.com"]),
        3,
        allow_external_services=True,
        allowed_external_hosts=(),
    ) == []

    monkeypatch.setattr(
        web,
        "fetch_document",
        lambda *a, **k: search.SearchDocument(
            url="https://example.com", title="", text="unrelated"
        ),
    )
    assert web._crawl_search(
        "court",
        SearchSettings(seed_urls=["https://example.com"]),
        3,
        allow_external_services=True,
        allowed_external_hosts=(),
    ) == []


def test_search_web_deduplicates_and_limits(monkeypatch) -> None:
    monkeypatch.setattr(
        web,
        "_local_search",
        lambda query, settings, limit: [
            search.SearchResult("a", "https://a"),
            search.SearchResult("b", "https://a"),
            search.SearchResult("c", "https://c"),
        ],
    )
    settings = SearchSettings(providers=["local"], max_results=1)
    assert len(web.search_web("x", settings=settings)) == 1
    assert len(web.search_web("x", settings=settings, limit=2)) == 2


def test_search_web_aggregates_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        web,
        "_local_search",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad")),
    )
    with pytest.raises(SearchError, match="No search provider"):
        web.search_web("x", settings=SearchSettings(providers=["local"]))
