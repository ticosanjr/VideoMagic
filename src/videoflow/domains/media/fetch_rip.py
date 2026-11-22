"""Bounded external video excerpts and sound effects."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .errors import InvalidRequestError
from .fetch_common import _bounded_float, _bounded_int, _clip, _require_query
from .fetch_service_base import FetchServiceBase
from .providers import (
    LocalAsset,
    YtDlpClient,
    freesound_license_filter,
    resolve_sfx_provider,
    safe_filename,
    validate_external_url,
)


class RipSfxMixin(FetchServiceBase):
    """yt-dlp excerpts and Freesound/local SFX acquisition."""

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
