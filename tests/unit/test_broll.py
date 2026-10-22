from pathlib import Path

import httpx

from videoflow.application.broll_providers import (
    LocalBrollProvider,
    PexelsBrollProvider,
)


def test_local_provider_ranks_matching_names(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "city-night.mp4").write_bytes(b"a")
    (assets / "studio.mp4").write_bytes(b"b")
    found = LocalBrollProvider(assets).search("city skyline", limit=2)
    assert found[0].path is not None and found[0].path.name == "city-night.mp4"
    assert found[0].license == "operator"


def test_pexels_provider_search_and_download(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/videos/search"):
            assert request.headers["Authorization"] == "secret"
            return httpx.Response(
                200,
                json={
                    "videos": [
                        {
                            "url": "https://pexels.example/video/1",
                            "user": {"name": "Creator"},
                            "video_files": [
                                {
                                    "file_type": "video/mp4",
                                    "width": 1280,
                                    "link": "https://cdn.example/1.mp4",
                                }
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(200, content=b"video-bytes")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = PexelsBrollProvider("secret", client=client)
    assets = provider.search("city", limit=1)
    assert len(assets) == 1
    assert assets[0].provider == "pexels"
    assert assets[0].license == "Pexels License"
    target = provider.download(assets[0], tmp_path / "clip.mp4")
    assert target.read_bytes() == b"video-bytes"
