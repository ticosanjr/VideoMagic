"""Intelligence provider status and model discovery routes."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from videoflow.application.intelligence import build_intelligence, telemetry


def register_intelligence_routes(app: FastAPI) -> None:
    """Register provider status, task routing, and model discovery."""

    @app.get("/api/v1/intelligence/status")
    def intelligence_status() -> dict[str, object]:
        intelligence = build_intelligence()
        return {
            "ok": True,
            "enabled": intelligence.config.enabled,
            "order": intelligence.config.provider_order,
            "providers": [asdict(item) for item in intelligence.status()],
            "telemetry": telemetry.snapshot(),
        }

    @app.get("/api/v1/intelligence/tasks")
    def intelligence_tasks() -> dict[str, object]:
        intelligence = build_intelligence()
        return {
            "ok": True,
            "default_order": intelligence.config.provider_order,
            "tasks": {
                key: value.model_dump(mode="json")
                for key, value in intelligence.config.tasks.items()
            },
        }

    @app.get("/api/v1/intelligence/models")
    def intelligence_models(provider: str = "opencode_v2") -> dict[str, object]:
        intelligence = build_intelligence()
        models = intelligence.models(provider)
        if not models:
            status = next(
                (item for item in intelligence.status() if item.provider == provider),
                None,
            )
            if status is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "ok": False,
                        "code": "provider_not_found",
                        "message": provider,
                    },
                )
        return {"ok": True, "provider": provider, "models": models}
