"""HTTP token/LAN/open authentication middleware."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from gpu_worker.api_common import PUBLIC_PATHS
from gpu_worker.http_auth import is_loopback_client as _is_loopback_client
from gpu_worker.http_auth import is_private_client as _is_private_client
from gpu_worker.http_auth import matches_allowlist as _matches_allowlist


def install_auth_middleware(app: Any, audit: Callable[[str, str, str, str], None]) -> None:
    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if request.url.path in PUBLIC_PATHS or request.url.path == "/health/":
            return await call_next(request)
        configured = str(app.state.runtime_token or "")
        supplied = request.headers.get("x-vf-token", "")
        valid = bool(
            configured
            and supplied
            and secrets.compare_digest(
                supplied.encode("utf-8"), configured.encode("utf-8")
            )
        )
        client_host = request.client.host if request.client else ""
        loopback = _is_loopback_client(client_host)
        lan_open = bool(
            app.state.settings.allow_lan_open
            and not app.state.settings.token_only
            and _is_private_client(client_host)
            and (
                not app.state.settings.allowed_clients
                or _matches_allowlist(client_host, app.state.settings.allowed_clients)
            )
        )
        if valid or lan_open or loopback:
            outcome = "token" if valid else ("loopback" if loopback else "lan_open")
            audit(client_host, request.url.path, request.method, outcome)
            app.state.request_count += 1
            app.state.clients[client_host] = time.time()
            if request.url.path not in {
                "/api/overview",
                "/api/jobs",
                "/api/logs",
                "/health",
                "/probe",
            } and not request.url.path.startswith("/ui"):
                app.state.last_request_at = time.time()
                app.state.last_request = {
                    "path": request.url.path,
                    "method": request.method,
                    "client": client_host,
                    "at": app.state.last_request_at,
                }
            return await call_next(request)
        audit(client_host, request.url.path, request.method, "denied")
        if not configured:
            return JSONResponse(
                status_code=503,
                content={"detail": "VF_GPU_TOKEN is not configured on the worker"},
            )
        return JSONResponse(
            status_code=401, content={"detail": "missing or invalid X-VF-Token"}
        )

