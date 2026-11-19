"""Read-only capability discovery for the MCP control panel."""

from __future__ import annotations

from fastapi import FastAPI

from videoflow.application.capabilities import (
    capability_manifest,
    external_services_allowed,
)


def register_discovery_routes(app: FastAPI) -> None:
    @app.get("/api/v1/capabilities")
    def capabilities(allow_external: bool = False) -> dict[str, object]:
        return {
            "ok": True,
            "external_services_allowed": external_services_allowed(allow_external),
            "capabilities": capability_manifest(allow_external_services=allow_external),
        }
