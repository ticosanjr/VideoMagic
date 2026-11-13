from __future__ import annotations

import json
from types import SimpleNamespace

from videoflow.application.asset_providers import search_assets
from videoflow.application.settings import AppSettings


class Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.content = json.dumps(payload).encode()
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _fake_get(routes):
    def get(url, **kwargs):
        for marker, payload in routes.items():
            if marker in url:
                return Response(payload)
        return Response({}, 404)

    return get


def test_pixabay_video_and_image(monkeypatch) -> None:
    monkeypatch.setenv("PIXABAY_API_KEY", "key")
    routes = {
        "/api/videos/": {
            "hits": [
                {
                    "tags": "evidence",
                    "pageURL": "https://pixabay.com/video/1",
                    "user": "creator",
                    "duration": 10,
                    "videos": {
                        "medium": {
                            "url": "https://cdn.example.com/v.mp4",
                            "width": 1280,
                            "height": 720,
                        }
                    },
                }
            ]
        },
        "/api/": {
            "hits": [
                {
                    "tags": "document",
                    "pageURL": "https://pixabay.com/photo/1",
                    "largeImageURL": "https://cdn.example.com/i.jpg",
                    "imageWidth": 1280,
                    "imageHeight": 720,
                }
            ]
        },
    }
    monkeypatch.setattr(
        "videoflow.application.asset_providers.search.httpx.get", _fake_get(routes)
    )
    results = search_assets(
        "evidence",
        providers=["pixabay"],
        settings=AppSettings(),
        media="all",
        limit=1,
        allow_external_services=True,
    )
    assert results[0].provider == "pixabay"
    assert results[0].license_status == "cleared"


def test_openverse_and_wikimedia(monkeypatch) -> None:
    routes = {
        "/v1/images/": {
            "results": [
                {
                    "title": "Photo",
                    "foreign_landing_url": "https://openverse.org/photo",
                    "url": "https://cdn.example.com/photo.jpg",
                    "license": "cc0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "creator": "Author",
                }
            ]
        },
        "/w/api.php": {
            "query": {
                "pages": {
                    "1": {
                        "title": "File:Document.jpg",
                        "imageinfo": [
                            {
                                "url": "https://upload.wikimedia.org/document.jpg",
                                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Document.jpg",
                                "extmetadata": {
                                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                                    "Artist": {"value": "<a>Author</a>"},
                                },
                            }
                        ],
                    }
                }
            }
        },
    }
    monkeypatch.setattr(
        "videoflow.application.asset_providers.search.httpx.get", _fake_get(routes)
    )
    results = search_assets(
        "document",
        providers=["openverse", "wikimedia"],
        settings=AppSettings(),
        media="all",
        limit=2,
        allow_external_services=True,
    )
    assert {item.provider for item in results} == {"openverse", "wikimedia"}
    assert any(item.license_status == "cc_review" for item in results)


def test_internet_archive_metadata(monkeypatch) -> None:
    routes = {
        "advancedsearch.php": {
            "response": {
                "docs": [
                    {
                        "identifier": "archive-1",
                        "title": "Archive video",
                        "mediatype": "movies",
                        "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                    }
                ]
            }
        },
        "/metadata/archive-1": {
            "files": [{"name": "video.mp4", "format": "MPEG4"}]
        },
    }
    monkeypatch.setattr(
        "videoflow.application.asset_providers.search.httpx.get", _fake_get(routes)
    )
    results = search_assets(
        "archive",
        providers=["internet_archive"],
        settings=AppSettings(),
        media="video",
        limit=1,
        allow_external_services=True,
    )
    assert results[0].page_url.endswith("/details/archive-1")
    assert results[0].download_url.endswith("video.mp4")


def test_youtube_search(monkeypatch) -> None:
    monkeypatch.setattr(
        "videoflow.application.asset_providers.search.find_binary", lambda name: "/bin/yt-dlp"
    )
    monkeypatch.setattr(
        "videoflow.application.asset_providers.search.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="abc\tEvidence clip\t600\tCreator\n",
            stderr="",
        ),
    )
    results = search_assets(
        "evidence",
        providers=["youtube"],
        settings=AppSettings(),
        media="video",
        limit=1,
        allow_external_services=True,
    )
    assert results[0].provider == "youtube"
    assert results[0].license_status == "fair_use_review"
    assert results[0].duration_sec == 600


def test_missing_keys_and_http_errors(monkeypatch) -> None:
    import pytest

    from videoflow.application.asset_providers import search
    from videoflow.domain.errors import CapabilityUnavailableError, SearchError

    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    with pytest.raises(CapabilityUnavailableError):
        search._pexels(
            "x",
            settings=AppSettings(),
            limit=1,
            media="all",
            allow_external_services=True,
            allowed_external_hosts=(),
        )
    with pytest.raises(CapabilityUnavailableError):
        search._pixabay(
            "x",
            settings=AppSettings(),
            limit=1,
            media="all",
            allow_external_services=True,
            allowed_external_hosts=(),
        )

    monkeypatch.setenv("PEXELS_API_KEY", "key")
    monkeypatch.setattr(
        search.httpx,
        "get",
        lambda *args, **kwargs: Response({}, 500),
    )
    with pytest.raises(SearchError, match="Pexels video"):
        search._pexels(
            "x",
            settings=AppSettings(),
            limit=1,
            media="video",
            allow_external_services=True,
            allowed_external_hosts=(),
        )
    with pytest.raises(SearchError, match="Wikimedia"):
        search._wikimedia(
            "x",
            limit=1,
            media="all",
            allow_external_services=True,
            allowed_external_hosts=(),
        )
    with pytest.raises(SearchError, match="Internet Archive"):
        search._internet_archive(
            "x",
            limit=1,
            media="all",
            allow_external_services=True,
            allowed_external_hosts=(),
        )


def test_openverse_wikimedia_and_archive_skip_bad_items(monkeypatch) -> None:
    routes = {
        "/v1/images/": {
            "results": [
                {"title": "ok", "url": "https://cdn/i.jpg"},
            ]
        },
        "/w/api.php": {
            "query": {
                "pages": {
                    "1": {"title": "No imageinfo"},
                    "2": {
                        "title": "File:Sound.ogg",
                        "imageinfo": [{"url": "https://cdn/sound.ogg"}],
                    },
                    "3": {
                        "title": "File:Video.mp4",
                        "imageinfo": [{"url": "https://cdn/video.mp4"}],
                    },
                }
            }
        },
        "advancedsearch.php": {
            "response": {
                "docs": [
                    {"title": "No id", "mediatype": "movies"},
                    {"identifier": "audio-1", "mediatype": "audio"},
                    {
                        "identifier": "meta-fail",
                        "mediatype": "movies",
                        "title": "Fail",
                    },
                    {"identifier": "no-file", "mediatype": "image"},
                ]
            }
        },
        "/metadata/meta-fail": {},
        "/metadata/no-file": {"files": [{"name": "file.txt"}]},
    }

    def get(url, **kwargs):
        if "advancedsearch.php" in url:
            return Response(routes["advancedsearch.php"])
        if "/v1/images/" in url:
            return Response(routes["/v1/images/"])
        if "/w/api.php" in url:
            return Response(routes["/w/api.php"])
        if "/metadata/meta-fail" in url:
            return Response({}, 500)
        if "/metadata/no-file" in url:
            return Response(routes["/metadata/no-file"])
        return Response({}, 404)

    monkeypatch.setattr(
        "videoflow.application.asset_providers.search.httpx.get", get
    )
    openverse = search_assets(
        "x",
        providers=["openverse"],
        settings=AppSettings(),
        media="image",
        limit=2,
        allow_external_services=True,
    )
    assert [item.provider for item in openverse] == ["openverse"]
    wikimedia = search_assets(
        "x",
        providers=["wikimedia"],
        settings=AppSettings(),
        media="all",
        limit=5,
        allow_external_services=True,
    )
    assert {item.download_url for item in wikimedia} == {
        "https://cdn/sound.ogg",
        "https://cdn/video.mp4",
    }
    archive = search_assets(
        "x",
        providers=["internet_archive"],
        settings=AppSettings(),
        media="all",
        limit=5,
        allow_external_services=True,
    )
    assert archive == []

    monkeypatch.setattr(
        "videoflow.application.asset_providers.search.httpx.get",
        lambda *args, **kwargs: Response({"results": []}, 500),
    )
    assert (
        search_assets(
            "x",
            providers=["openverse"],
            settings=AppSettings(),
            allow_external_services=True,
        )
        == []
    )
    assert (
        search_assets(
            "x",
            providers=["openverse"],
            settings=AppSettings(),
            media="video",
            allow_external_services=True,
        )
        == []
    )


def test_youtube_failures_and_aggregate_errors(monkeypatch) -> None:
    import pytest

    from videoflow.application.asset_providers import search
    from videoflow.domain.errors import CapabilityUnavailableError, SearchError

    assert (
        search._youtube(
            "x",
            limit=1,
            media="image",
            allow_external_services=True,
            allowed_external_hosts=(),
        )
        == []
    )
    monkeypatch.setattr(search, "find_binary", lambda name: None)
    with pytest.raises(CapabilityUnavailableError):
        search._youtube(
            "x",
            limit=1,
            media="all",
            allow_external_services=True,
            allowed_external_hosts=(),
        )

    monkeypatch.setattr(search, "find_binary", lambda name: "/bin/yt-dlp")
    monkeypatch.setattr(
        search.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="bad"),
    )
    with pytest.raises(SearchError, match="YouTube search failed"):
        search._youtube(
            "x",
            limit=1,
            media="all",
            allow_external_services=True,
            allowed_external_hosts=(),
        )

    monkeypatch.setattr(
        search.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="bad-line\nid\tTitle\tnope\tUploader\n",
            stderr="",
        ),
    )
    results = search._youtube(
        "x",
        limit=1,
        media="all",
        allow_external_services=True,
        allowed_external_hosts=(),
    )
    assert results[0].duration_sec == 0.0

    with pytest.raises(SearchError, match="No asset provider"):
        search_assets(
            "x",
            providers=["unknown", "pexels"],
            settings=AppSettings(),
            allow_external_services=False,
        )
