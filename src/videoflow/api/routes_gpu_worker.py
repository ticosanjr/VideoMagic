"""Windows GPU worker package routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from videoflow.application.win_worker_kit import build_worker_kit, kit_info
from videoflow.domain.errors import VideoFlowError


class WindowsKitRequest(BaseModel):
    token: str = ""
    worker_id: str = ""
    shared_windows_path: str = ""
    ffmpeg_path: str = ""
    include_worker_source: bool = True


def register_gpu_worker_routes(app: FastAPI) -> None:
    """Register the personal Windows worker kit download and metadata."""

    @app.post("/api/v1/gpu-worker/package")
    def package_gpu_worker(payload: WindowsKitRequest | None = None) -> FileResponse:
        request = payload or WindowsKitRequest()
        try:
            result = build_worker_kit(
                token=request.token,
                worker_id=request.worker_id,
                shared_windows_path=request.shared_windows_path,
                ffmpeg_path=Path(request.ffmpeg_path) if request.ffmpeg_path else None,
                include_worker_source=request.include_worker_source,
            )
        except (OSError, VideoFlowError) as exc:
            raise HTTPException(
                status_code=500,
                detail={"ok": False, "code": "win_kit_failed", "message": str(exc)},
            ) from exc
        return FileResponse(
            result.path,
            media_type="application/zip",
            filename=result.path.name,
        )

    @app.get("/api/v1/gpu-worker/package/info")
    def package_gpu_worker_info() -> dict[str, object]:
        info = kit_info()
        if info is None:
            return {
                "ok": False,
                "code": "win_kit_missing",
                "message": "No Windows worker kit has been generated yet.",
            }
        return info


__all__ = ["WindowsKitRequest", "register_gpu_worker_routes"]
