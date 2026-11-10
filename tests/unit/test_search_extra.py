from __future__ import annotations

from pathlib import Path

from videoflow.application import search
from videoflow.application.search import SearchDocument, SearchSettings, search_web


class Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload


def test_wikipedia_and_internet_archive(monkeypatch) -> None:
    payloads = {
        "w/api.php": {
            "query": {
                "search": [
                    {
                        "title": "Case",
                        "snippet": "<span>Court</span> record",
                        "timestamp": "2020-01-01",
                    }
                ]
            }
        },
        "advancedsearch.php": {
            "response": {"docs": [{"identifier": "ia-1", "title": "Archive"}]}
        },
    }

    def fake_get(url, **kwargs):
        for marker, payload in payloads.items():
            if marker in url:
                return Response(payload)
        return Response({}, 404)

    monkeypatch.setattr(search.web.httpx, "get", fake_get)
    settings = SearchSettings(
        providers=["wikipedia", "internet_archive"],
        wikipedia_language="en",
    )
    results = search_web(
        "court", settings=settings, allow_external_services=True, limit=2
    )
    assert {item.provider for item in results} == {"wikipedia", "internet_archive"}
    assert "Court" in results[0].snippet


def test_crawl_seed_matches_text(monkeypatch) -> None:
    monkeypatch.setattr(
        search.web,
        "fetch_document",
        lambda url, *args, **kwargs: SearchDocument(
            url=url, title="Seed", text="court corruption evidence", provider="web"
        ),
    )
    settings = SearchSettings(
        providers=["crawl"], seed_urls=["https://example.com/page"]
    )
    results = search_web(
        "corruption", settings=settings, allow_external_services=True
    )
    assert results[0].provider == "crawl"
    assert "corruption" in results[0].snippet


def test_robots_parser_and_private_host(monkeypatch) -> None:
    class Robots:
        status_code = 200
        text = "User-agent: *\nDisallow: /blocked\n"

    monkeypatch.setattr(search.documents.httpx, "get", lambda *args, **kwargs: Robots())
    assert search.documents._robots_allowed("https://example.com/blocked", timeout=1) is False
    assert search.documents._robots_allowed("https://example.com/open", timeout=1) is True


def test_local_search_skips_missing_roots(tmp_path: Path) -> None:
    settings = SearchSettings(providers=["local"], local_paths=[str(tmp_path / "missing")])
    assert search_web("anything", settings=settings) == []
