from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application.search import (
    SearchBlockedError,
    SearchSettings,
    fetch_document,
    html_text,
    search_web,
    source_manifest,
)


def test_local_search_and_file_fetch(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "case.md").write_text(
        "# Guaruja triplex\n\nA corruption investigation with court records.\n",
        encoding="utf-8",
    )
    (corpus / "unrelated.txt").write_text("weather and sports\n", encoding="utf-8")
    settings = SearchSettings(local_paths=[str(corpus)], providers=["local"])
    results = search_web("corruption court", settings=settings)
    assert len(results) == 1
    assert results[0].provider == "local"
    document = fetch_document(results[0].url, settings)
    assert "Guaruja" in document.text
    assert source_manifest(results, [document])[0]["fetched"] is True


def test_html_extraction_skips_scripts() -> None:
    title, text = html_text(
        "<html><head><title>Dossier</title><script>alert(1)</script></head>"
        "<body><h1>Case</h1><p>Court record.</p></body></html>"
    )
    assert title == "Dossier"
    assert "Court record" in text
    assert "alert" not in text


def test_private_host_is_blocked() -> None:
    with pytest.raises(SearchBlockedError):
        fetch_document(
            "http://127.0.0.1/private",
            SearchSettings(),
            allow_external_services=True,
        )


def test_searxng_provider(monkeypatch, tmp_path: Path) -> None:
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {
                        "title": "A result",
                        "url": "https://example.com/a",
                        "content": "snippet",
                    }
                ]
            }

    monkeypatch.setattr(
        "videoflow.application.search.httpx.get", lambda *args, **kwargs: FakeResponse()
    )
    settings = SearchSettings(
        providers=["searxng"],
        searxng_url="http://127.0.0.1:8080",
        allow_network=True,
    )
    results = search_web(
        "query", settings=settings, allow_external_services=True
    )
    assert results[0].provider == "searxng"
    assert results[0].url == "https://example.com/a"


def test_fetch_cache_and_robots(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    calls = {"fetch": 0}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        content = b"<html><title>Page</title><body>Body text</body></html>"
        encoding = "utf-8"

        def json(self):
            return {}

    def fake_get(url, **kwargs):
        calls["fetch"] += 1
        return FakeResponse()

    monkeypatch.setattr("videoflow.application.search.httpx.get", fake_get)
    monkeypatch.setattr(
        "videoflow.application.search._assert_public_url", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "videoflow.application.search._robots_allowed", lambda *a, **k: True
    )
    first = fetch_document(
        "https://example.com/page", SearchSettings(), allow_external_services=True
    )
    second = fetch_document(
        "https://example.com/page", SearchSettings(), allow_external_services=True
    )
    assert first.title == "Page"
    assert second.text == first.text
    assert calls["fetch"] == 1


def test_robots_disallow(monkeypatch) -> None:
    monkeypatch.setattr(
        "videoflow.application.search._assert_public_url", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "videoflow.application.search._robots_allowed", lambda *a, **k: False
    )
    with pytest.raises(SearchBlockedError):
        fetch_document(
            "https://example.com/blocked",
            SearchSettings(),
            allow_external_services=True,
        )
