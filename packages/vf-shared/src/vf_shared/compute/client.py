"""Minimal synchronous client for a VideoFlow GPU worker."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

import httpx

from vf_shared.compute.models import WorkerHealth

from .client_common import (
    GPUWorkerError,
    GPUWorkerUnsupported,
    _json_object,
)
from .client_jobs import ClientJobsMixin
from .client_transfer import ClientTransferMixin


class GPUWorkerClient(ClientTransferMixin, ClientJobsMixin):
    """HTTP client for one GPU worker."""

    def __init__(
        self,
        base_url: str,
        token: str = "",
        timeout: float = 30.0,
        *,
        transport: httpx.BaseTransport | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = float(timeout)
        self._headers = {"X-VF-Token": token} if token else {}
        self._http = http_client or httpx.Client(
            timeout=self.timeout,
            transport=transport,
            headers=self._headers,
        )
        self.transfer_stats: dict[str, float] = {
            "upload_bytes": 0.0,
            "upload_seconds": 0.0,
            "upload_dedup": 0.0,
            "download_bytes": 0.0,
            "download_seconds": 0.0,
        }
        self._transfer_lock = threading.Lock()


    def reset_transfer_stats(self) -> None:
        with self._transfer_lock:
            for key in self.transfer_stats:
                self.transfer_stats[key] = 0.0


    def _record_transfer(self, key: str, value: float) -> None:
        with self._transfer_lock:
            self.transfer_stats[key] = self.transfer_stats.get(key, 0.0) + max(0.0, value)


    def __enter__(self) -> GPUWorkerClient:
        return self


    def __exit__(self, *_exc: object) -> None:
        self.close()


    def close(self) -> None:
        self._http.close()


    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = dict(self._headers)
        extra = kwargs.pop("headers", None)
        if isinstance(extra, Mapping):
            headers.update({str(key): str(value) for key, value in extra.items()})
        try:
            response = self._http.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                timeout=timeout if timeout is not None else self.timeout,
                **kwargs,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GPUWorkerError(
                f"worker request failed: {exc.response.status_code} {exc.response.text[:200]}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise GPUWorkerError(f"worker request failed: {exc}") from exc
        return response


    def health(self, timeout: float | None = None) -> WorkerHealth:
        """Fetch worker health."""

        response = self._request("GET", "/health", timeout=timeout)
        return WorkerHealth.from_payload(_json_object(response))


__all__ = ["GPUWorkerClient", "GPUWorkerError", "GPUWorkerUnsupported"]
