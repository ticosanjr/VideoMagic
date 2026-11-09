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
