"""Minimal synchronous client for a VideoFlow GPU worker."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from vf_compute.models import JobStatus, WorkerHealth

_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled", "canceled", "done", "error"})


class GPUWorkerError(RuntimeError):
    """Raised when a GPU worker request fails or returns an invalid payload."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GPUWorkerUnsupported(GPUWorkerError):
    """Raised when the worker does not implement an optional transport endpoint."""


def _safe_segment(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not _SEGMENT_RE.fullmatch(value)
        or value in {".", ".."}
    ):
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise GPUWorkerError("worker returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise GPUWorkerError("worker returned a non-object JSON payload")
    return {str(key): value for key, value in payload.items()}


def _atomic_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class GPUWorkerClient:
    """Synchronous HTTP client for a GPU worker.

    The client only talks to the configured base URL. Job ids, artifact names
    and route fragments are validated before they are placed in a URL, and
    downloads always target a caller-provided local path.
    """

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
            response = self._request(
                "POST",
                "/artifacts",
                files={"file": ("artifact.bin", bytes(content))},
            )
            return self._artifact_id(response)
        source = Path(content)
        if not source.is_file():
            raise FileNotFoundError(f"artifact not found: {source}")
        try:
            return self.upload_resumable(source, progress=progress, cancel=cancel)
        except GPUWorkerUnsupported:
            return self._upload_multipart(source)

    def _upload_multipart(self, source: Path) -> str:
        with source.open("rb") as handle:
            response = self._request(
                "POST",
                "/artifacts",
                files={"file": (source.name, handle, "application/octet-stream")},
            )
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
    ) -> str:
        """Upload a file with resumable chunks and SHA-256 verification."""

        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"artifact not found: {path}")
        size = path.stat().st_size
        digest = _sha256_file(path)
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
            return str(existing)
        upload_id = str(payload.get("upload_id") or "")
        if not upload_id:
            raise GPUWorkerError("worker did not return an upload id")
        offset = int(payload.get("offset") or 0)
        chunk_size = max(
            1,
            min(int(payload.get("chunk_size") or 8 * 1024 * 1024), 64 * 1024 * 1024),
        )
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

    def submit(
        self,
        capability: str,
        params: Mapping[str, Any] | None = None,
        inputs: list[str] | None = None,
        *,
        shared_root: str | None = None,
        shared_inputs: list[str] | None = None,
        shared_outputs: list[str] | None = None,
    ) -> str:
        """Submit a job to ``POST /jobs/{capability}`` and return its job id.

        When ``shared_root`` or ``shared_inputs`` is provided the request is
        marked ``shared=true`` and includes the relative paths under both
        ``input_paths`` and ``shared_inputs`` so workers can mount the
        workspace directly. ``shared_outputs`` asks the worker to write results
        into the same mounted workspace.
        """

        if not capability:
            raise ValueError("capability is required")
        clean_capability = _safe_segment(capability, "capability")
        shared = (
            shared_root is not None
            or bool(shared_inputs)
            or bool(shared_outputs)
        )
        body: dict[str, Any] = {
            "params": dict(params or {}),
            "inputs": list(inputs or []),
            "shared": shared,
        }
        if shared:
            input_paths = list(shared_inputs or [])
            body["shared_inputs"] = input_paths
            body["input_paths"] = input_paths
            body["shared_outputs"] = list(shared_outputs or [])

        response = self._request(
            "POST", f"/jobs/{quote(clean_capability, safe='')}", json=body
        )
        payload = _json_object(response)
        job_id = payload.get("job_id") or payload.get("id")
        if not job_id:
            raise GPUWorkerError("worker did not return a job id")
        return str(job_id)

    def overview(self, timeout: float | None = None) -> dict[str, Any]:
        response = self._request("GET", "/api/overview", timeout=timeout)
        return _json_object(response)

    def status(self, job_id: str) -> JobStatus:
        """Fetch one job status."""

        clean_id = _safe_segment(job_id, "job id")
        response = self._request("GET", f"/jobs/{quote(clean_id, safe='')}")
        return JobStatus.from_payload(_json_object(response), job_id=clean_id)

    def probe(self) -> dict[str, Any]:
        """Run the worker's real CUDA/NVENC/matte probe."""

        try:
            response = self._request("POST", "/probe")
        except GPUWorkerError as exc:
            if exc.status_code in {404, 405}:
                raise GPUWorkerUnsupported(
                    "worker does not implement /probe",
                    status_code=exc.status_code,
                ) from exc
            raise
        return _json_object(response)

    def unload_models(self, name: str = "") -> dict[str, Any]:
        """Ask the worker to free one model or every loaded model."""

        response = self._request(
            "POST",
            "/models/unload",
            json={"name": str(name or "")},
        )
        return _json_object(response)

    def validate_shared(self, path: str) -> dict[str, Any]:
        """Ask the worker to validate one shared write path."""

        response = self._request(
            "POST",
            "/shared/validate",
            json={"path": str(path or "")},
        )
        return _json_object(response)

    def wait(self, job_id: str, timeout: float = 300.0, poll: float = 0.5) -> JobStatus:
        """Poll until a job reaches a terminal state or ``timeout`` elapses."""

        deadline = time.monotonic() + max(timeout, 0.0)
        delay = max(poll, 0.0)
        last = self.status(job_id)
        while not last.done:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"job {job_id} did not finish within {timeout}s (state={last.state})"
                )
            if delay:
                time.sleep(delay)
            last = self.status(job_id)
        return last

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
        paths: list[Path] = []
        for name in names:
            item = by_name.get(name, {})
            paths.append(
                self.download(
                    job_id,
                    name,
                    directory / Path(name).name,
                    expected_sha256=str(item.get("sha256") or ""),
                    progress=progress,
                    cancel=cancel,
                )
            )
        return paths


__all__ = [
    "GPUWorkerClient",
    "GPUWorkerError",
    "GPUWorkerUnsupported",
    "TERMINAL_STATES",
]
