# GPU worker HTTP streaming

HTTP is the default transport between the VideoFlow controller and the Windows
GPU worker. A shared mount is an optional accelerator; it is never required.

## Why

- Works without SMB, mapped drives, or a shared folder.
- Streams large files instead of loading them into memory.
- Resumes uploads and downloads after a dropped connection.
- Verifies SHA-256 after every transfer.
- Falls back to HTTP automatically when a shared-mount write fails.

## Upload protocol

```text
POST /artifacts/init
  {"filename": "input.mp4", "size": 123456789, "sha256": "...", "chunk_size": 8388608}
  -> {"upload_id": "...", "offset": 0, "size": 123456789, "chunk_size": 8388608}

PATCH /artifacts/{upload_id}
  Content-Range: bytes 0-8388607/123456789
  body: raw bytes
  -> {"received": 8388608, "size": 123456789}

POST /artifacts/{upload_id}/complete
  -> {"artifact_id": "<sha256>", "sha256": "<sha256>", "bytes": 123456789}

GET /artifacts/{upload_id}/status
  -> {"received": 8388608, "size": 123456789}
```

`POST /artifacts/init` with the same SHA-256 and size returns the existing
incomplete upload and its current offset, so the controller can resume.

The legacy multipart `POST /artifacts` endpoint remains available. The client
falls back to it automatically when the worker does not implement the
resumable endpoints.

## Download protocol

```text
GET /jobs/{job_id}/artifacts
  -> {"artifacts": [{"name": "render.mp4", "size": 123, "sha256": "..."}]}

HEAD /jobs/{job_id}/artifact/{name}
  -> Content-Length, Accept-Ranges, X-VF-Sha256, ETag

GET /jobs/{job_id}/artifact/{name}
  Range: bytes=1048576-
  -> 206 Partial Content, Content-Range, X-VF-Sha256
```

The controller writes to a `.part` file, verifies SHA-256, then renames the
file into place. An interrupted download resumes from the `.part` offset.

## Shared mount fallback

The worker writes shared outputs to a temporary file, flushes and fsyncs it,
then renames it into the shared folder. If Windows returns `WinError 32`, the
file is empty, or the mount disappeared:

- the worker keeps the artifact in its local artifact directory;
- the job still succeeds;
- `shared_error` is recorded;
- the controller downloads the artifact over HTTP and reports
  `transport: "http_fallback"` with `degraded: true`.

The controller also retries shared-file size checks briefly to absorb SMB
metadata caching.

## Limits

- Default maximum artifact size: 8 GB (`VF_GPU_MAX_UPLOAD_MB`).
- Upload chunk: 8 MB by default, configurable up to 64 MB.
- Download chunk: 1 MB.
- Retries: 3 attempts with backoff for transient transfer errors.

## Security

- Every non-health endpoint requires `X-VF-Token`.
- Artifact names are validated; range and path traversal are rejected.
- The worker is intended for a private LAN. Do not expose port 8766 to the
  internet.
