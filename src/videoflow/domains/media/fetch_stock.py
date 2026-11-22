"""Stock B-roll and image acquisition."""

from __future__ import annotations

import tempfile
from typing import Any

import httpx

from .errors import (
    InvalidRequestError,
    McpFetchError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from .fetch_common import _bounded_int, _check_orientation, _require_query
from .fetch_service_base import FetchServiceBase
from .providers import (
    GalleryDLClient,
    LocalAsset,
    OpenverseClient,
    WikimediaClient,
    env_value,
    resolve_keyed_provider,
)


class StockMixin(FetchServiceBase):
    """Stock video and image searches with keyed and keyless providers."""

    def fetch_stock_broll(
        self,
        project_id: str,
        query: str,
        orientation: str = "landscape",
        min_duration: int = 4,
        max_results: int = 5,
        provider: str = "auto",
    ) -> dict[str, Any]:
        workspace = self._workspace(project_id)
        query = _require_query(query)
        orientation = _check_orientation(orientation)
        min_duration = _bounded_int(min_duration, name="min_duration", minimum=0, maximum=3600)
        max_results = _bounded_int(max_results, name="max_results", minimum=1, maximum=50)
        provider_name, client = resolve_keyed_provider(
            provider,
            env=self._env(),
            media="video",
            client=self._http_client(),
        )
        params = {
            "orientation": orientation,
            "min_duration": min_duration,
            "max_results": max_results,
        }
        request = {
            "tool": "fetch_stock_broll",
            "provider": provider_name,
            "query": query,
            **params,
        }
        key = workspace.key({**request, "project_id": workspace.project_id})
        cached = self._cached(workspace, key, provider=provider_name, request=request)
        if cached is not None:
            return cached
        candidates = client.search_videos(
            query,
            orientation=orientation,
            min_duration=min_duration,
            max_results=max_results,
        )
        return self._materialize_remote(
            workspace,
            key,
            kind="broll",
            provider_name=provider_name,
            candidates=candidates,
            downloader=client,
            query=query,
            params=params,
            request=request,
        )

    def fetch_stock_images(
        self,
        project_id: str,
        query: str,
        count: int = 5,
        keyless: bool = True,
        provider: str = "auto",
    ) -> dict[str, Any]:
        workspace = self._workspace(project_id)
        query = _require_query(query)
        count = _bounded_int(count, name="count", minimum=1, maximum=50)
        requested = str(provider or "auto").strip().lower()
        if requested not in {
            "auto",
            "pexels",
            "pixabay",
            "openverse",
            "wikimedia",
            "gallery-dl",
            "gallery_dl",
        }:
            raise InvalidRequestError(
                f"Unknown provider {provider!r}; use 'auto', 'pexels', 'pixabay', "
                "'openverse', 'wikimedia', or 'gallery-dl'."
            )
        orientation = "landscape"
        provider_name = ""
        client: Any = None
        keyless_chain: list[str] = []
        if requested in {"auto", "pexels", "pixabay"}:
            try:
                provider_name, client = resolve_keyed_provider(
                    requested,
                    env=self._env(),
                    media="images",
                    client=self._http_client(),
                )
            except ProviderUnavailableError:
                if not keyless or requested != "auto":
                    raise
                keyless_chain = ["openverse", "wikimedia", "gallery-dl"]
                provider_name = "gallery-dl"
        elif requested in {"openverse", "wikimedia"}:
            keyless_chain = [requested]
            provider_name = requested
        else:
            provider_name = "gallery-dl"

        if keyless_chain and keyless_chain[0] != "gallery-dl":
            factories = {"openverse": OpenverseClient, "wikimedia": WikimediaClient}
            last_failure: Exception | None = None
            for candidate_name in keyless_chain:
                if candidate_name == "gallery-dl":
                    provider_name = "gallery-dl"
                    break
                try:
                    candidate_client = factories[candidate_name](
                        client=self._http_client()
                    )
                    candidates = candidate_client.search_images(
                        query, count=count, orientation=orientation
                    )
                    if not candidates:
                        raise ProviderResponseError(
                            f"{candidate_name} returned no images for {query!r}."
                        )
                    request = {
                        "tool": "fetch_stock_images",
                        "provider": candidate_name,
                        "query": query,
                        "count": count,
                        "keyless": True,
                        "orientation": orientation,
                    }
                    key = workspace.key({**request, "project_id": workspace.project_id})
                    cached = self._cached(
                        workspace, key, provider=candidate_name, request=request
                    )
                    if cached is not None:
                        return cached
                    return self._materialize_remote(
                        workspace,
                        key,
                        kind="images",
                        provider_name=candidate_name,
                        candidates=candidates,
                        downloader=candidate_client,
                        query=query,
                        params={"count": count, "keyless": True},
                        request=request,
                    )
                except (McpFetchError, httpx.HTTPError) as exc:  # try the next source
                    last_failure = exc
                    provider_name = candidate_name
            if requested in {"openverse", "wikimedia"}:
                raise ProviderResponseError(
                    f"{requested} image search failed: {last_failure}",
                    detail={"query": query},
                )

        params = {"count": count, "keyless": bool(keyless), "orientation": orientation}
        request = {
            "tool": "fetch_stock_images",
            "provider": provider_name,
            "query": query,
            **params,
        }
        key = workspace.key({**request, "project_id": workspace.project_id})
        cached = self._cached(workspace, key, provider=provider_name, request=request)
        if cached is not None:
            return cached

        if provider_name == "gallery-dl":
            gallery = GalleryDLClient(binary=self.gallery_dl_binary)
            with tempfile.TemporaryDirectory(prefix="vf-mcp-fetch-gallery-") as temporary:
                paths = gallery.fetch_images(
                    query,
                    count=count,
                    destination=temporary,
                    allowed_hosts=self._allowed_hosts(),
                    url_template=env_value(self._env(), "VF_GALLERY_DL_URL_TEMPLATE"),
                )
                candidates = [
                    LocalAsset(
                        path=path,
                        metadata={
                            "name": path.name,
                            "query": query,
                            "keyless": True,
                        },
                        license={
                            "provider": "gallery-dl",
                            "license": "unknown",
                            "license_url": "",
                            "status": "unknown",
                            "commercial_use": False,
                            "attribution_required": True,
                            "attribution": "Keyless source; verify rights before publishing.",
                        },
                    )
                    for path in paths[:count]
                ]
                return self._materialize_local(
                    workspace,
                    key,
                    kind="images",
                    provider_name="gallery-dl",
                    candidates=candidates,
                    query=query,
                    params=params,
                    request=request,
                )

        candidates = client.search_images(
            query,
            count=count,
            orientation=orientation,
        )
        return self._materialize_remote(
            workspace,
            key,
            kind="images",
            provider_name=provider_name,
            candidates=candidates,
            downloader=client,
            query=query,
            params=params,
            request=request,
        )
