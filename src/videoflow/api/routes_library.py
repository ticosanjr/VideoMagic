"""Asset library, NLE validation, and run-history routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from videoflow.application.assets import (
    get_asset,
    list_assets,
    remove_asset,
    scan_directory,
    update_tags,
)
from videoflow.application.nle_validation import validate_nle_exports
from videoflow.domain.errors import PathNotFoundError, VideoFlowError
from videoflow.domain.paths import resolve_allowed
from videoflow.engine.history import read_runs
from videoflow.runtime import allowed_roots


class AssetScanRequest(BaseModel):
    directory: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    recursive: bool = True


class AssetTagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)


class ExportValidationRequest(BaseModel):
    output: str = Field(min_length=1)


def register_library_routes(app: FastAPI) -> None:
    """Register asset-library, export-validation, and run-history routes."""

    @app.get("/api/v1/assets")
    def list_assets_route(
        q: str = "",
        kind: str = "",
        limit: int = 500,
    ) -> dict[str, object]:
        return {"ok": True, "assets": list_assets(q, kind, limit)}

    @app.post("/api/v1/assets/scan")
    def scan_assets(request: AssetScanRequest) -> dict[str, object]:
        directory = resolve_allowed(Path(request.directory), allowed_roots())
        records = scan_directory(
            directory,
            tags=request.tags,
            recursive=request.recursive,
        )
        return {"ok": True, "scanned": len(records), "assets": records}

    @app.patch("/api/v1/assets/{asset_id}")
    def tag_asset(asset_id: str, request: AssetTagsRequest) -> dict[str, object]:
        asset = update_tags(asset_id, request.tags)
        if asset is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "asset_not_found", "message": asset_id},
            )
        return {"ok": True, "asset": asset}

    @app.delete("/api/v1/assets/{asset_id}")
    def delete_asset(asset_id: str) -> dict[str, object]:
        if not remove_asset(asset_id):
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "asset_not_found", "message": asset_id},
            )
        return {"ok": True}

    @app.get("/api/v1/assets/{asset_id}/file")
    def asset_file(asset_id: str) -> FileResponse:
        asset = get_asset(asset_id)
        if asset is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "asset_not_found", "message": asset_id},
            )
        try:
            path = resolve_allowed(Path(str(asset["path"])), allowed_roots())
        except VideoFlowError as exc:
            raise HTTPException(status_code=403, detail=exc.to_dict()) from exc
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "asset_file_not_found"},
            )
        return FileResponse(path, filename=path.name)

    @app.post("/api/v1/exports/validate")
    def validate_exports(request: ExportValidationRequest) -> dict[str, object]:
        resolved = resolve_allowed(Path(request.output), allowed_roots())
        if (resolved / "timeline.fcpxml").is_file() or any(
            resolved.glob("*.fcpxml")
        ):
            directory = resolved
        else:
            directory = resolved / "exports"
        if not directory.is_dir():
            raise PathNotFoundError(f"Export directory does not exist: {directory}")
        return validate_nle_exports(directory)

    @app.get("/api/v1/runs")
    def list_runs(
        output: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, object]:
        resolved = resolve_allowed(Path(output), allowed_roots())
        return {
            "ok": True,
            "runs": read_runs(resolved, limit=limit, offset=offset),
            "total": len(read_runs(resolved)),
        }
