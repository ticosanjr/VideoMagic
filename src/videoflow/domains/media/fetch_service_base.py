"""FetchService connection, workspace and materialization primitives."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

import httpx

from .errors import DownloadError, McpFetchError, ProviderResponseError
from .fetch_workspace import Asset, Workspace
from .fetch_workspace_utils import utc_now
from .providers import LocalAsset, RemoteAsset, env_value, parse_allowed_hosts


class FetchServiceBase:
    """Provider orchestration shared by the stock, rip and SFX tools."""


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
