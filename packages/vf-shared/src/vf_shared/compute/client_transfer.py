"""Resumable uploads, manifests and artifact downloads."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .client_common import (
    GPUWorkerError,
    GPUWorkerUnsupported,
    _json_object,
    _safe_segment,
    _sha256_file,
)


class ClientTransferMixin:
    """Upload and download artifacts with resumable retries."""

    def upload_artifact(
        self,
        content: bytes | bytearray | memoryview | str | Path,
        *,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> str:
        """Upload bytes or a local file and return the worker artifact id.

        Local files use the resumable chunked protocol when the worker supports
        it and fall back to multipart for older workers.
        """

        if isinstance(content, (bytes, bytearray, memoryview)):
            payload = bytes(content)
            digest = hashlib.sha256(payload).hexdigest()
            existing = self.probe_artifact(digest)
            if existing is not None:
                self._record_transfer("upload_dedup", 1)
                return existing
            response = self._request(
                "POST",
                "/artifacts",
                files={"file": ("artifact.bin", payload)},
            )
            return self._artifact_id(response)
        source = Path(content)
        if not source.is_file():
            raise FileNotFoundError(f"artifact not found: {source}")
        digest = _sha256_file(source)
        existing = self.probe_artifact(digest)
        if existing is not None:
            self._record_transfer("upload_dedup", 1)
            return existing
        try:
            return self.upload_resumable(
                source, progress=progress, cancel=cancel, digest=digest
            )
        except GPUWorkerUnsupported:
            return self._upload_multipart(source)

    def probe_artifact(self, sha256: str) -> str | None:
        """Return the worker artifact id when the content hash is already cached.

        Workers older than the HEAD endpoint answer 404/405; callers then use the
        existing resumable init path, which also deduplicates by SHA-256.
        """

        clean = str(sha256 or "").strip().lower()
        if len(clean) != 64 or any(char not in "0123456789abcdef" for char in clean):
            raise ValueError(f"invalid SHA-256: {sha256!r}")
        try:
            response = self._request(
                "HEAD",
                f"/artifacts/{quote(clean, safe='')}",
                timeout=self.timeout,
            )
        except GPUWorkerError as exc:
            if exc.status_code in {404, 405}:
                return None
            raise
        return response.headers.get("X-VF-Artifact-Id") or clean


    def _upload_multipart(self, source: Path) -> str:
        started = time.perf_counter()
        with source.open("rb") as handle:
            response = self._request(
                "POST",
                "/artifacts",
                files={"file": (source.name, handle, "application/octet-stream")},
            )
        self._record_transfer("upload_bytes", source.stat().st_size)
        self._record_transfer("upload_seconds", time.perf_counter() - started)
        return self._artifact_id(response)


    def _artifact_id(self, response: httpx.Response) -> str:
        payload = _json_object(response)
        artifact_id = payload.get("artifact_id") or payload.get("id")
        if not artifact_id:
            raise GPUWorkerError("worker did not return an artifact id")
        return str(artifact_id)


    def upload_resumable(
        self,
        source: str | Path,
        *,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        digest: str = "",
    ) -> str:
        """Upload a file with resumable chunks and SHA-256 verification."""

        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"artifact not found: {path}")
        size = path.stat().st_size
        digest = str(digest or _sha256_file(path)).strip().lower()
        try:
            init = self._request(
                "POST",
                "/artifacts/init",
                json={
                    "filename": path.name,
                    "size": size,
                    "sha256": digest,
                    "chunk_size": 8 * 1024 * 1024,
                },
            )
        except GPUWorkerError as exc:
            if exc.status_code in {404, 405}:
                raise GPUWorkerUnsupported(
                    "worker does not support resumable uploads",
                    status_code=exc.status_code,
                ) from exc
            raise
        payload = _json_object(init)
        existing = payload.get("artifact_id")
        if existing and payload.get("complete"):
            self._record_transfer("upload_dedup", 1)
            return str(existing)
        upload_id = str(payload.get("upload_id") or "")
        if not upload_id:
            raise GPUWorkerError("worker did not return an upload id")
        offset = int(payload.get("offset") or 0)
        chunk_size = max(
            1,
            min(int(payload.get("chunk_size") or 8 * 1024 * 1024), 64 * 1024 * 1024),
        )
        initial_offset = offset
        upload_started = time.perf_counter()
        with path.open("rb") as handle:
            handle.seek(offset)
            while offset < size:
                if cancel is not None and cancel():
                    raise GPUWorkerError("upload cancelled")
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                end = offset + len(chunk) - 1
                response: httpx.Response | None = None
                last_error: GPUWorkerError | None = None
                for attempt in range(3):
                    try:
                        response = self._request(
                            "PATCH",
                            f"/artifacts/{quote(upload_id, safe='')}",
                            content=chunk,
                            timeout=300.0,
                            headers={
                                "Content-Range": f"bytes {offset}-{end}/{size}",
                                "Content-Type": "application/octet-stream",
                            },
                        )
                        break
                    except GPUWorkerError as exc:
                        if exc.status_code in {404, 405}:
                            raise GPUWorkerUnsupported(
                                "worker does not support resumable uploads",
                                status_code=exc.status_code,
                            ) from exc
                        last_error = exc
                        if exc.status_code is not None and exc.status_code < 500:
                            raise
                        time.sleep(0.5 * (attempt + 1))
                if response is None:
                    raise last_error or GPUWorkerError("upload chunk failed")
                result = _json_object(response)
                offset = int(result.get("received") or (offset + len(chunk)))
                if progress is not None:
                    progress(offset, size)
        complete = self._request(
            "POST",
            f"/artifacts/{quote(upload_id, safe='')}/complete",
        )
        self._record_transfer("upload_bytes", max(0, size - initial_offset))
        self._record_transfer("upload_seconds", time.perf_counter() - upload_started)
        return self._artifact_id(complete)


    def artifact_manifest(self, job_id: str) -> list[dict[str, Any]]:
        """Return name, size, and SHA-256 for every artifact of a job."""

        clean_id = _safe_segment(job_id, "job id")
        try:
            response = self._request(
                "GET",
                f"/jobs/{quote(clean_id, safe='')}/artifacts",
            )
        except GPUWorkerError as exc:
            if exc.status_code in {404, 405}:
                return []
            raise
        payload = _json_object(response)
        items = payload.get("artifacts")
        if not isinstance(items, list):
            return []
        manifest: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            manifest.append(
                {
                    "name": str(item.get("name") or ""),
                    "size": int(item.get("size") or 0),
                    "sha256": str(item.get("sha256") or ""),
                }
            )
        return [item for item in manifest if item["name"]]


    def download(
        self,
        job_id: str,
        name: str,
        target: str | Path,
        *,
        expected_sha256: str = "",
        resume: bool = True,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> Path:
        """Stream a named job artifact to disk with optional resume."""

        clean_id = _safe_segment(job_id, "job id")
        clean_name = _safe_segment(name, "artifact name")
        download_started = time.perf_counter()
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.parent / f".{destination.name}.part"
        offset = partial.stat().st_size if resume and partial.is_file() else 0
        headers = dict(self._headers)
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"
        url = (
            f"{self.base_url}/jobs/{quote(clean_id, safe='')}"
            f"/artifact/{quote(clean_name, safe='')}"
        )
        try:
            with self._http.stream(
                "GET",
                url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout, read=300.0),
            ) as response:
                if response.status_code == 416 and offset > 0:
                    partial.unlink(missing_ok=True)
                    return self.download(
                        job_id,
                        name,
                        destination,
                        expected_sha256=expected_sha256,
                        resume=False,
                        progress=progress,
                        cancel=cancel,
                    )
                response.raise_for_status()
                append = response.status_code == 206 and offset > 0
                digest = hashlib.sha256()
                written = 0
                if append:
                    with partial.open("rb") as existing:
                        while True:
                            chunk = existing.read(1024 * 1024)
                            if not chunk:
                                break
                            digest.update(chunk)
                            written += len(chunk)
                mode = "ab" if append else "wb"
                with partial.open(mode) as handle:
                    for chunk in response.iter_bytes(1024 * 1024):
                        if cancel is not None and cancel():
                            raise GPUWorkerError("download cancelled")
                        handle.write(chunk)
                        digest.update(chunk)
                        written += len(chunk)
                        if progress is not None:
                            total = int(response.headers.get("content-length") or 0)
                            if total > 0:
                                total += offset if append else 0
                            progress(written, total)
                    handle.flush()
                    os.fsync(handle.fileno())
                expected = str(
                    expected_sha256 or response.headers.get("x-vf-sha256") or ""
                ).strip().lower()
                if expected and digest.hexdigest() != expected:
                    partial.unlink(missing_ok=True)
                    raise GPUWorkerError("artifact SHA-256 does not match")
                os.replace(partial, destination)
                self._record_transfer("download_bytes", written)
                self._record_transfer(
                    "download_seconds", time.perf_counter() - download_started
                )
                return destination
        except httpx.HTTPStatusError as exc:
            raise GPUWorkerError(
                f"worker request failed: {exc.response.status_code} {exc.response.text[:200]}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise GPUWorkerError(f"worker request failed: {exc}") from exc


    def download_all(
        self,
        job_id: str,
        names: list[str],
        target_dir: str | Path,
        *,
        manifest: list[dict[str, Any]] | None = None,
        progress: Callable[[int, int], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        max_parallel: int = 3,
    ) -> list[Path]:
        """Download every named artifact and verify the manifest hashes."""

        directory = Path(target_dir)
        directory.mkdir(parents=True, exist_ok=True)
        if manifest is None:
            manifest = self.artifact_manifest(job_id)
        by_name = {
            str(item.get("name") or ""): item
            for item in manifest
            if isinstance(item, Mapping)
        }

        def fetch(name: str) -> Path:
            item = by_name.get(name, {})
            return self.download(
                job_id,
                name,
                directory / Path(name).name,
                expected_sha256=str(item.get("sha256") or ""),
                progress=progress,
                cancel=cancel,
            )

        workers = max(1, min(int(max_parallel), 8, max(1, len(names))))
        if workers == 1 or len(names) <= 1:
            return [fetch(name) for name in names]
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(fetch, names))
