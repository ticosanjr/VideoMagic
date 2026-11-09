"""Asset upload, list, and delete routes."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from videoflow.application.fonts import delete_fonts, list_fonts, save_font
from videoflow.application.images import delete_images, list_images, save_image
from videoflow.application.music import delete_music, list_music, save_music
from videoflow.application.sfx import delete_sfx, list_sfx, save_sfx
from videoflow.domain.errors import FilesystemError


def _invalid(kind: str, exc: FilesystemError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"ok": False, "code": f"{kind}_invalid", "message": str(exc)},
    )


def register_asset_routes(app: FastAPI) -> None:
    """Register the local music, SFX, image, and font asset routes."""

    @app.get("/api/v1/assets/music")
    def music() -> dict[str, object]:
        return {"ok": True, "music": list_music()}

    @app.post("/api/v1/assets/music", status_code=201)
    async def upload_music(name: str, request: Request) -> dict[str, object]:
        try:
            asset = save_music(name, await request.body())
        except FilesystemError as exc:
            raise _invalid("music", exc) from exc
        return {"ok": True, "music": asset}

    @app.get("/api/v1/assets/sfx")
    def sfx() -> dict[str, object]:
        return {"ok": True, "sfx": list_sfx()}

    @app.post("/api/v1/assets/sfx", status_code=201)
    async def upload_sfx(name: str, request: Request) -> dict[str, object]:
        try:
            asset = save_sfx(name, await request.body())
        except FilesystemError as exc:
            raise _invalid("sfx", exc) from exc
        return {"ok": True, "sfx": asset}

    @app.delete("/api/v1/assets/sfx/{name}")
    def remove_sfx(name: str) -> dict[str, object]:
        delete_sfx(name)
        return {"ok": True, "deleted": name}

    @app.get("/api/v1/assets/images")
    def images() -> dict[str, object]:
        return {"ok": True, "images": list_images()}

    @app.post("/api/v1/assets/images", status_code=201)
    async def upload_image(name: str, request: Request) -> dict[str, object]:
        try:
            asset = save_image(name, await request.body())
        except FilesystemError as exc:
            raise _invalid("image", exc) from exc
        return {"ok": True, "image": asset}

    @app.delete("/api/v1/assets/music/{name}")
    def remove_music(name: str) -> dict[str, object]:
        delete_music(name)
        return {"ok": True, "deleted": name}

    @app.delete("/api/v1/assets/images/{name}")
    def remove_image(name: str) -> dict[str, object]:
        delete_images(name)
        return {"ok": True, "deleted": name}

    @app.delete("/api/v1/assets/fonts/{name}")
    def remove_font(name: str) -> dict[str, object]:
        delete_fonts(name)
        return {"ok": True, "deleted": name}

    @app.get("/api/v1/assets/fonts")
    def fonts() -> dict[str, object]:
        return {"ok": True, "fonts": list_fonts()}

    @app.post("/api/v1/assets/fonts", status_code=201)
    async def upload_font(name: str, request: Request) -> dict[str, object]:
        try:
            asset = save_font(name, await request.body())
        except FilesystemError as exc:
            raise _invalid("font", exc) from exc
        return {"ok": True, "font": asset}
