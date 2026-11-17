"""VideoFlow 2.90 fetch MCP server.

Tools acquire stock footage, images, SFX, and bounded video excerpts into a
project workspace. Every result is an absolute path with a metadata sidecar and
a license sidecar; repeated requests reuse the cached asset.
"""

from __future__ import annotations

import math
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

import httpx
from mcp.server import MCPServer

from .contracts import Asset, Workspace
from .errors import (
    DownloadError,
    InvalidRequestError,
    McpFetchError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from .providers import (
    GalleryDLClient,
    LocalAsset,
    RemoteAsset,
    YtDlpClient,
    env_value,
    freesound_license_filter,
    parse_allowed_hosts,
    resolve_keyed_provider,
    resolve_sfx_provider,
    safe_filename,
    utc_now,
    validate_external_url,
)

SERVER_NAME = "VideoFlow Fetch"
ORIENTATIONS = {"landscape", "portrait", "square"}
TOOL_DESCRIPTIONS = {
    "fetch_stock_broll": (
        "Fetch stock B-roll video into the project workspace. Returns absolute "
        "asset paths, metadata, and license sidecars."
    ),
    "fetch_stock_images": (
        "Fetch stock images into the project workspace, using Pexels/Pixabay keys "
        "or keyless gallery-dl."
    ),
    "rip_video_segment": (
        "Download one bounded video or audio segment with yt-dlp and record a "
        "fair-use review sidecar."
    ),
    "fetch_sfx": (
        "Fetch a sound effect from Freesound or VF_SFX_DIR into the project "
        "workspace with license metadata."
    ),
}


def _require_query(query: str) -> str:
    value = str(query or "").strip()
    if not value:
        raise InvalidRequestError("query must not be empty.")
    return value


def _check_orientation(value: str) -> str:
    normalized = str(value or "landscape").strip().lower()
    if normalized not in ORIENTATIONS:
        raise InvalidRequestError(
            f"orientation must be one of {sorted(ORIENTATIONS)}, got {value!r}."
        )
    return normalized


def _bounded_int(value: int, *, name: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidRequestError(f"{name} must be an integer.") from exc
    if not minimum <= number <= maximum:
        raise InvalidRequestError(f"{name} must be between {minimum} and {maximum}, got {number}.")
    return number


def _bounded_float(
    value: float,
    *,
    name: str,
    minimum: float,
    maximum: float | None = None,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidRequestError(f"{name} must be a number.") from exc
    if not math.isfinite(number) or number < minimum:
        raise InvalidRequestError(f"{name} must be a finite number >= {minimum}.")
    if maximum is not None and number > maximum:
        raise InvalidRequestError(f"{name} must be <= {maximum}.")
    return number


def _clip(start_time: float, end_time: float) -> dict[str, float]:
    return {"start": round(start_time, 3), "end": round(end_time, 3)}


class FetchService:
    """Provider orchestration, workspace materialization, and idempotency."""

    def __init__(
        self,
        *,
        workspace_root: str | Path | None = None,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
        env: Mapping[str, str] | None = None,
        gallery_dl_binary: str = "gallery-dl",
        yt_dlp_binary: str = "yt-dlp",
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser() if workspace_root else None
        self.transport = transport
        self._client = client
        self._owns_client = client is None
        self._env_override = dict(env) if env is not None else None
        self.gallery_dl_binary = gallery_dl_binary
        self.yt_dlp_binary = yt_dlp_binary

    def _env(self) -> Mapping[str, str]:
        return self._env_override if self._env_override is not None else os.environ

    def _http_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=30.0,
                follow_redirects=True,
                transport=self.transport,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            if self._owns_client:
                self._client.close()
            self._client = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _workspace(self, project_id: str) -> Workspace:
        root = self.workspace_root
        if root is None:
            override = env_value(self._env(), "VF_WORKSPACE_ROOT")
            root = Path(override).expanduser() if override else None
        return Workspace(project_id, root=root)

    def _allowed_hosts(self) -> tuple[str, ...]:
        return parse_allowed_hosts(env_value(self._env(), "VF_ALLOWED_EXTERNAL_HOSTS"))

    @staticmethod
    def _result(
        *,
        provider: str,
        assets: list[Asset],
        request: Mapping[str, Any],
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        cached = bool(assets) and all(asset.cached for asset in assets)
        return {
            "ok": True,
            "cached": cached,
            "provider": provider,
            "request": dict(request),
            "assets": [asset.to_dict() for asset in assets],
            "warnings": warnings or [],
        }

    def _cached(
        self,
        workspace: Workspace,
        key: str,
        *,
        provider: str,
        request: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        assets = workspace.load_assets(key)
        if assets is None:
            return None
        return self._result(provider=provider, assets=assets, request=request)

    def _materialize_remote(
        self,
        workspace: Workspace,
        key: str,
        *,
        kind: str,
        provider_name: str,
        candidates: list[RemoteAsset],
        downloader: Any,
        query: str,
        params: Mapping[str, Any],
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        assets: list[Asset] = []
        warnings: list[str] = []
        last_error: McpFetchError | None = None
        with tempfile.TemporaryDirectory(prefix="vf-mcp-fetch-") as temporary:
            for index, candidate in enumerate(candidates):
                suffix = Path(candidate.suggested_filename).suffix or ".bin"
                target = Path(temporary) / f"{index:03d}{suffix}"
                try:
                    downloader.download(candidate.download_url, target)
                except DownloadError as exc:
                    last_error = exc
                    warnings.append(f"{candidate.page_url or candidate.download_url}: {exc}")
                    continue
                metadata = {
                    **candidate.metadata,
                    "provider": candidate.provider,
                    "page_url": candidate.page_url,
                    "download_url": candidate.download_url,
                    "creator": candidate.creator,
                    "query": query,
                    "params": dict(params),
                    "license_status": candidate.status,
                    "retrieved_at": utc_now(),
                }
                asset = workspace.import_file(
                    target,
                    kind=kind,
                    name=candidate.suggested_filename or target.name,
                    provider=candidate.provider,
                    metadata=metadata,
                    license=candidate.to_license(),
                    idempotency_key=key,
                    move=True,
                )
                assets.append(asset)
        if not assets:
            if last_error is not None:
                raise last_error
            raise ProviderResponseError(
                f"{provider_name} returned no downloadable assets for {query!r}."
            )
        workspace.save_manifest(key, assets, request)
        return self._result(
            provider=provider_name,
            assets=assets,
            request=request,
            warnings=warnings,
        )

    def _materialize_local(
        self,
        workspace: Workspace,
        key: str,
        *,
        kind: str,
        provider_name: str,
        candidates: list[LocalAsset],
        query: str,
        params: Mapping[str, Any],
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        assets: list[Asset] = []
        for candidate in candidates:
            metadata = {
                **candidate.metadata,
                "provider": provider_name,
                "page_url": str(candidate.path),
                "download_url": "",
                "query": query,
                "params": dict(params),
                "retrieved_at": utc_now(),
            }
            assets.append(
                workspace.import_file(
                    candidate.path,
                    kind=kind,
                    name=str(candidate.metadata.get("name") or candidate.path.name),
                    provider=provider_name,
                    metadata=metadata,
                    license=candidate.license,
                    idempotency_key=key,
                )
            )
        if not assets:
            raise ProviderResponseError(f"{provider_name} returned no assets for {query!r}.")
        workspace.save_manifest(key, assets, request)
        return self._result(provider=provider_name, assets=assets, request=request)

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
        if requested not in {"auto", "pexels", "pixabay", "gallery-dl", "gallery_dl"}:
            raise InvalidRequestError(
                f"Unknown provider {provider!r}; use 'auto', 'pexels', 'pixabay', or 'gallery-dl'."
            )
        orientation = "landscape"
        provider_name = ""
        client: Any = None
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
                provider_name = "gallery-dl"
        else:
            provider_name = "gallery-dl"

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

    def rip_video_segment(
        self,
        project_id: str,
        url: str,
        start_time: float,
        end_time: float,
        audio_only: bool = False,
        max_height: int = 1080,
    ) -> dict[str, Any]:
        workspace = self._workspace(project_id)
        allowed_hosts = self._allowed_hosts()
        url = validate_external_url(url, allowed_hosts)
        start_time = _bounded_float(start_time, name="start_time", minimum=0.0)
        end_time = _bounded_float(end_time, name="end_time", minimum=0.0)
        if end_time <= start_time:
            raise InvalidRequestError("end_time must be greater than start_time.")
        max_height = _bounded_int(max_height, name="max_height", minimum=144, maximum=4320)
        params = {
            "start_time": start_time,
            "end_time": end_time,
            "audio_only": bool(audio_only),
            "max_height": max_height,
            "url": url,
        }
        request = {
            "tool": "rip_video_segment",
            "provider": "yt-dlp",
            **params,
        }
        key = workspace.key({**request, "project_id": workspace.project_id})
        cached = self._cached(workspace, key, provider="yt-dlp", request=request)
        if cached is not None:
            return cached

        kind = "sfx" if audio_only else "broll"
        ytdlp = YtDlpClient(binary=self.yt_dlp_binary)
        with tempfile.TemporaryDirectory(prefix="vf-mcp-fetch-ytdlp-") as temporary:
            path = ytdlp.download_segment(
                url,
                start_time=start_time,
                end_time=end_time,
                audio_only=bool(audio_only),
                max_height=max_height,
                destination=temporary,
                allowed_hosts=allowed_hosts,
            )
            host = safe_filename(Path(url.split("://", 1)[-1].split("/", 1)[0]))
            name = f"yt-dlp-{host}-{start_time:g}-{end_time:g}{path.suffix}"
            candidate = LocalAsset(
                path=path,
                metadata={
                    "provider": "yt-dlp",
                    "name": name,
                    "page_url": url,
                    "download_url": url,
                    "creator": None,
                    "query": "",
                    "clip": _clip(start_time, end_time),
                    "audio_only": bool(audio_only),
                    "max_height": max_height,
                },
                license={
                    "provider": "yt-dlp",
                    "license": "Unknown (external excerpt)",
                    "license_url": "",
                    "status": "fair_use_review",
                    "commercial_use": False,
                    "attribution_required": True,
                    "attribution": f"Excerpt from {url}; confirm fair-use before publishing.",
                },
            )
            return self._materialize_local(
                workspace,
                key,
                kind=kind,
                provider_name="yt-dlp",
                candidates=[candidate],
                query="",
                params={**params, "name": name},
                request=request,
            )

    def fetch_sfx(
        self,
        project_id: str,
        query: str,
        max_duration: float = 5.0,
        license_filter: str = "cc0",
        provider: str = "auto",
    ) -> dict[str, Any]:
        workspace = self._workspace(project_id)
        query = _require_query(query)
        max_duration = _bounded_float(max_duration, name="max_duration", minimum=0.0)
        freesound_license_filter(license_filter)
        license_filter = str(license_filter or "any").strip().lower()
        provider_name, client = resolve_sfx_provider(
            provider,
            env=self._env(),
            client=self._http_client(),
        )
        params = {
            "max_duration": max_duration,
            "license_filter": license_filter,
        }
        request = {
            "tool": "fetch_sfx",
            "provider": provider_name,
            "query": query,
            **params,
        }
        key = workspace.key({**request, "project_id": workspace.project_id})
        cached = self._cached(workspace, key, provider=provider_name, request=request)
        if cached is not None:
            return cached

        if provider_name == "freesound":
            candidates = client.search_sfx(
                query,
                max_duration=max_duration,
                license_filter=license_filter,
                max_results=5,
            )
            return self._materialize_remote(
                workspace,
                key,
                kind="sfx",
                provider_name="freesound",
                candidates=candidates,
                downloader=client,
                query=query,
                params=params,
                request=request,
            )

        local_candidates = client.search(
            query,
            max_duration=max_duration,
            license_filter=license_filter,
            max_results=5,
        )
        return self._materialize_local(
            workspace,
            key,
            kind="sfx",
            provider_name="local",
            candidates=local_candidates,
            query=query,
            params=params,
            request=request,
        )


def fetch_stock_broll(
    project_id: str,
    query: str,
    orientation: str = "landscape",
    min_duration: int = 4,
    max_results: int = 5,
    provider: str = "auto",
) -> dict[str, Any]:
    """Fetch stock B-roll video into the project workspace."""

    with FetchService() as service:
        return service.fetch_stock_broll(
            project_id,
            query,
            orientation,
            min_duration,
            max_results,
            provider,
        )


def fetch_stock_images(
    project_id: str,
    query: str,
    count: int = 5,
    keyless: bool = True,
    provider: str = "auto",
) -> dict[str, Any]:
    """Fetch stock images into the project workspace."""

    with FetchService() as service:
        return service.fetch_stock_images(project_id, query, count, keyless, provider)


def rip_video_segment(
    project_id: str,
    url: str,
    start_time: float,
    end_time: float,
    audio_only: bool = False,
    max_height: int = 1080,
) -> dict[str, Any]:
    """Download a bounded external video/audio segment."""

    with FetchService() as service:
        return service.rip_video_segment(
            project_id,
            url,
            start_time,
            end_time,
            audio_only,
            max_height,
        )


def fetch_sfx(
    project_id: str,
    query: str,
    max_duration: float = 5.0,
    license_filter: str = "cc0",
    provider: str = "auto",
) -> dict[str, Any]:
    """Fetch a sound effect into the project workspace."""

    with FetchService() as service:
        return service.fetch_sfx(
            project_id,
            query,
            max_duration,
            license_filter,
            provider,
        )


def build_server(service: FetchService | None = None) -> MCPServer:
    """Build the fetch MCP server, optionally with an injected service."""

    mcp = MCPServer(
        SERVER_NAME,
        version="2.91.7",
        instructions=(
            "Project-scoped stock media acquisition. Every asset lands under the "
            "project workspace with metadata and license sidecars."
        ),
    )
    active = service or FetchService()

    mcp.add_tool(
        active.fetch_stock_broll,
        name="fetch_stock_broll",
        description=TOOL_DESCRIPTIONS["fetch_stock_broll"],
    )
    mcp.add_tool(
        active.fetch_stock_images,
        name="fetch_stock_images",
        description=TOOL_DESCRIPTIONS["fetch_stock_images"],
    )
    mcp.add_tool(
        active.rip_video_segment,
        name="rip_video_segment",
        description=TOOL_DESCRIPTIONS["rip_video_segment"],
    )
    mcp.add_tool(
        active.fetch_sfx,
        name="fetch_sfx",
        description=TOOL_DESCRIPTIONS["fetch_sfx"],
    )
    return mcp


def main() -> None:
    """Run the fetch server over stdio."""

    build_server().run("stdio")


__all__ = [
    "FetchService",
    "build_server",
    "fetch_sfx",
    "fetch_stock_broll",
    "fetch_stock_images",
    "main",
    "rip_video_segment",
]
