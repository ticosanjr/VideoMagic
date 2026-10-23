"""Local FastAPI application. Binds to loopback. No authentication in v1."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, Response

from videoflow import __version__
from videoflow.api.routes import register_routes
from videoflow.application.jobs import JobManager
from videoflow.application.publishing import start_scheduler, stop_scheduler
from videoflow.domain.constants import DEFAULT_API_HOST, DEFAULT_API_PORT
from videoflow.engine.batch import BatchManager
from videoflow.runtime import portable_home, ui_dir

UI_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


def create_app(
    *,
    ui: Path | None = None,
    with_mcp: bool = False,
    jobs: JobManager | None = None,
    start_publisher: bool = False,
) -> FastAPI:
    """Build the loopback app.

    ``with_mcp`` mounts the MCP server and starts its session manager. Tests that
    only exercise the JSON API leave it off.
    """

    manager = jobs or JobManager(store_dir=portable_home() / "jobs")
    batches = BatchManager(manager, store_dir=portable_home() / "batches")
    mcp_app = None
    lifespan = None
    if with_mcp:
        from videoflow.mcp_server.server import build_server

        mcp = build_server(manager, batches)
        mcp_app = mcp.streamable_http_app(streamable_http_path="/")

        @asynccontextmanager
        async def mcp_lifespan(_app: FastAPI) -> AsyncIterator[None]:
            async with mcp.session_manager.run():
                yield

        lifespan = mcp_lifespan

    app = FastAPI(
        title="VideoFlow",
        version=__version__,
        description="Local non-destructive video pre-edit pipeline.",
        lifespan=lifespan,
    )
    _install_common(app)
    app.state.jobs = manager
    app.state.batches = batches

    @app.middleware("http")
    async def cache_and_version_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        path = request.url.path
        response.headers["X-VideoFlow-Version"] = __version__
        if path in {"/", "/index.html"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        elif path.startswith("/_app/immutable/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/_app/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


    if start_publisher:
        @app.on_event("startup")
        def _start_publish_scheduler() -> None:
            if os.environ.get("VIDEOWFLOW_PUBLISH_SCHEDULER", "1") != "0":
                start_scheduler()

        @app.on_event("shutdown")
        def _stop_publish_scheduler() -> None:
            stop_scheduler()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "videoflow", "version": __version__}

    register_routes(app, manager, batches)

    if mcp_app is not None:
        app.mount("/mcp", mcp_app)

        @app.api_route(
            "/mcp",
            methods=["GET", "POST", "DELETE"],
            include_in_schema=False,
        )
        def mcp_no_trailing_slash(_request: Request) -> RedirectResponse:
            return RedirectResponse(url="/mcp/", status_code=307)

    static = ui if ui is not None else None
    if static is not None and (static / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(static), html=True), name="ui")
    else:

        @app.get("/")
        def root() -> dict[str, object]:
            return {
                "service": "videoflow",
                "version": __version__,
                "ui": False,
                "endpoints": ["/health", "/api/v1/system", "/api/v1/jobs"],
                "hint": "Run the CLI with `videoflow run` or build the UI.",
            }

    return app


def create_http_app(
    ui: Path | None = None,
    *,
    jobs: JobManager | None = None,
) -> FastAPI:
    """Loopback app with API routes, MCP HTTP, and an optional static rack UI."""

    return create_app(
        with_mcp=True,
        ui=ui if ui is not None else ui_dir(),
        jobs=jobs,
        start_publisher=True,
    )


def _install_common(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(UI_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )


__all__ = [
    "DEFAULT_API_HOST",
    "DEFAULT_API_PORT",
    "UI_ORIGINS",
    "create_app",
    "create_http_app",
]
