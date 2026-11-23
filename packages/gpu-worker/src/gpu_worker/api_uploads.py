"""Resumable artifact upload routes."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from gpu_worker.api_models import UploadInit
from gpu_worker.artifacts import ArtifactTooLarge
from gpu_worker.security import UnsafePathError


def register_upload_routes(app: FastAPI, ctx: Any) -> None:
    artifacts = ctx.artifacts
    uploads = ctx.uploads

    @app.post("/artifacts")
    async def upload_artifact(
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        try:
            record = await run_in_threadpool(artifacts.save_upload, file.file, file.filename)
        except ArtifactTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except UnsafePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            await file.close()
        return {"artifact_id": record.id, "sha256": record.id, "bytes": record.size}

    @app.head("/artifacts/{artifact_id}")
    def head_artifact(artifact_id: str) -> Response:
        """Check the content-addressed cache without downloading the artifact."""

        clean = artifact_id.strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", clean) is None:
            raise HTTPException(status_code=400, detail="artifact id must be SHA-256")
        record = artifacts.get(clean)
        if record is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return Response(
            status_code=200,
            headers={"X-VF-Artifact-Id": record.id},
        )

    @app.post("/artifacts/init")
    def init_artifact(body: UploadInit) -> dict[str, Any]:
        existing = artifacts.get(body.sha256) if body.sha256 else None
        if existing is not None:
            return {
                "upload_id": f"artifact:{existing.id}",
                "offset": existing.size,
                "size": existing.size,
                "chunk_size": body.chunk_size,
                "sha256": existing.id,
                "artifact_id": existing.id,
                "complete": True,
            }
        try:
            session = uploads.create(
                filename=body.filename,
                size=body.size,
                sha256=body.sha256,
                chunk_size=body.chunk_size,
            )
        except ArtifactTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "upload_id": session.id,
            "offset": session.received,
            "size": session.size,
            "chunk_size": session.chunk_size,
            "sha256": session.sha256,
        }

    @app.patch("/artifacts/{upload_id}")
    async def append_artifact(upload_id: str, request: Request) -> dict[str, Any]:
        session = uploads.get(upload_id)
        if session is None:
            raise HTTPException(status_code=404, detail="upload session not found")
        content_range = request.headers.get("content-range", "")
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range.strip())
        if match is None:
            raise HTTPException(
                status_code=400,
                detail="Content-Range must be 'bytes start-end/total'",
            )
        start, end, total = (int(part) for part in match.groups())
        if total != session.size:
            raise HTTPException(status_code=400, detail="Content-Range total mismatch")
        if end < start or end >= session.size:
            raise HTTPException(status_code=400, detail="Content-Range is outside the upload")
        data = await request.body()
        if len(data) != end - start + 1:
            raise HTTPException(
                status_code=400,
                detail="Content-Range length does not match the request body",
            )
        try:
            updated = await run_in_threadpool(uploads.append, upload_id, start, data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "upload_id": updated.id,
            "received": updated.received,
            "size": updated.size,
        }

    @app.post("/artifacts/{upload_id}/complete")
    async def complete_artifact(upload_id: str) -> dict[str, Any]:
        try:
            record = await run_in_threadpool(uploads.complete, upload_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ArtifactTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "artifact_id": record.id,
            "sha256": record.id,
            "bytes": record.size,
            "filename": record.filename,
        }

    @app.get("/artifacts/{upload_id}/status")
    def artifact_upload_status(upload_id: str) -> dict[str, Any]:
        session = uploads.get(upload_id)
        if session is None:
            raise HTTPException(status_code=404, detail="upload session not found")
        return {
            "upload_id": session.id,
            "received": session.received,
            "size": session.size,
            "chunk_size": session.chunk_size,
            "sha256": session.sha256,
        }
