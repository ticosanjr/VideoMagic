"""Service, model, plugin, and settings administration routes."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from videoflow.application.model_downloads import downloads as model_downloads
from videoflow.application.models import (
    install_model,
    list_models,
    register_local_model,
    remove_model,
    update_model,
    verify_model,
)
from videoflow.application.plugins import (
    list_plugins,
    load_plugins,
    set_plugin_enabled,
)
from videoflow.application.service_definitions import (
    ServiceDefinition,
    delete_definition,
    list_definitions,
    list_statuses,
    read_logs,
    save_definition,
    start_service,
    status_service,
    stop_service,
)
from videoflow.application.services import (
    append_server_log,
    discover_services,
    read_server_log,
    server_log_path,
    stop_other_services,
    stop_service_pid,
)
from videoflow.application.settings import (
    AppSettings,
    env_overrides,
    load_settings,
    save_settings,
)


class ModelInstallRequest(BaseModel):
    allow_external_services: bool = True


class LocalModelRequest(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = ""
    capability: str = "other"
    path: str = Field(min_length=1)
    kind: str = "local"
    license: str = ""


def _plugins_payload(items: list[dict[str, object]]) -> dict[str, object]:
    from videoflow import plugin_api

    return {
        "ok": True,
        "plugins": items,
        "panels": [{"id": key, **value} for key, value in plugin_api.PANELS.items()],
    }


def register_admin_routes(app: FastAPI) -> None:
    """Register service, model, plugin, and settings routes."""

    @app.get("/api/v1/services/definitions")
    def service_definitions_list() -> dict[str, object]:
        return {
            "ok": True,
            "services": [item.model_dump(mode="json") for item in list_definitions()],
            "statuses": list_statuses(),
        }

    @app.put("/api/v1/services/definitions/{service_id}")
    def service_definition_save(service_id: str, request: ServiceDefinition) -> dict[str, object]:
        if request.id != service_id:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "service_id_mismatch", "message": service_id},
            )
        saved = save_definition(request)
        return {"ok": True, "service": saved.model_dump(mode="json")}

    @app.delete("/api/v1/services/definitions/{service_id}")
    def service_definition_delete(service_id: str) -> dict[str, object]:
        delete_definition(service_id)
        return {"ok": True, "deleted": service_id}

    @app.post("/api/v1/services/definitions/{service_id}/start")
    def service_definition_start(service_id: str) -> dict[str, object]:
        status = start_service(service_id)
        return {"ok": True, "service": status}

    @app.post("/api/v1/services/definitions/{service_id}/stop")
    def service_definition_stop(service_id: str) -> dict[str, object]:
        status = stop_service(service_id)
        return {"ok": True, "service": status}

    @app.get("/api/v1/services/definitions/{service_id}/status")
    def service_definition_status(service_id: str) -> dict[str, object]:
        status = status_service(service_id)
        return {"ok": True, "service": status}

    @app.get("/api/v1/services/definitions/{service_id}/logs")
    def service_definition_logs(service_id: str, lines: int = 200) -> dict[str, object]:
        status = status_service(service_id)
        return {
            "ok": True,
            "service": status,
            "text": read_logs(service_id, lines=max(1, min(2000, lines))),
        }

    @app.get("/api/v1/services")
    def services_list(request: Request) -> dict[str, object]:
        services = [
            item.to_dict()
            for item in discover_services(current_pid=os.getpid())
            if item.kind != "launcher"
        ]
        return {
            "ok": True,
            "pid": os.getpid(),
            "port": getattr(request.app.state, "port", None),
            "log_path": str(server_log_path()),
            "services": services,
        }

    @app.get("/api/v1/services/log")
    def services_log(lines: int = 200) -> dict[str, object]:
        return {
            "ok": True,
            "path": str(server_log_path()),
            "text": read_server_log(lines),
        }

    @app.post("/api/v1/services/cleanup")
    def services_cleanup() -> dict[str, object]:
        result = stop_other_services(current_pid=os.getpid())
        append_server_log(f"cleanup result={result}")
        return {"ok": True, **result}

    @app.post("/api/v1/services/{pid}/stop")
    def services_stop(pid: int) -> dict[str, object]:
        services = {item.pid: item for item in discover_services(current_pid=os.getpid())}
        target = services.get(pid)
        if target is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "code": "service_not_found",
                    "message": f"VideoFlow service {pid} was not found.",
                },
            )
        if target.current or target.protected:
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "code": "service_protected",
                    "message": "Use Stop service for the current process.",
                },
            )
        stopped = stop_service_pid(pid)
        append_server_log(f"stop requested pid={pid} stopped={stopped}")
        return {"ok": True, "stopped": stopped, "pid": pid}

    @app.get("/api/v1/models")
    def models_list() -> dict[str, object]:
        return {"ok": True, "models": list_models()}

    @app.post("/api/v1/models/{model_id}/install")
    def models_install(
        model_id: str, request: ModelInstallRequest | None = None
    ) -> dict[str, object]:
        payload = install_model(
            model_id,
            allow_network=bool(request.allow_external_services) if request else True,
        )
        return {"ok": True, "model": payload}

    @app.post("/api/v1/models/{model_id}/download", status_code=202)
    def models_download(
        model_id: str, request: ModelInstallRequest | None = None
    ) -> dict[str, object]:
        payload = model_downloads.start(
            model_id,
            allow_network=bool(request.allow_external_services) if request else True,
        )
        return {"ok": True, "download": payload.to_dict()}

    @app.get("/api/v1/models/downloads")
    def models_downloads() -> dict[str, object]:
        return {"ok": True, "downloads": model_downloads.list()}

    @app.delete("/api/v1/models/downloads/{model_id}")
    def models_download_cancel(model_id: str) -> dict[str, object]:
        payload = model_downloads.cancel(model_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "download_not_found", "message": model_id},
            )
        return {"ok": True, "download": payload.to_dict()}

    @app.post("/api/v1/models/local", status_code=201)
    def models_register_local(request: LocalModelRequest) -> dict[str, object]:
        payload = register_local_model(
            model_id=request.id,
            label=request.label or request.id,
            capability=request.capability,
            path=request.path,
            kind=request.kind,
            license=request.license,
        )
        return {"ok": True, "model": payload}

    @app.post("/api/v1/models/{model_id}/update")
    def models_update(
        model_id: str, request: ModelInstallRequest | None = None
    ) -> dict[str, object]:
        payload = update_model(
            model_id,
            allow_network=bool(request.allow_external_services) if request else True,
        )
        return {"ok": True, "model": payload}

    @app.post("/api/v1/models/{model_id}/verify")
    def models_verify(model_id: str) -> dict[str, object]:
        payload = verify_model(model_id)
        return {"ok": True, "verification": payload}

    @app.delete("/api/v1/models/{model_id}")
    def models_remove(model_id: str) -> dict[str, object]:
        remove_model(model_id)
        return {"ok": True, "removed": model_id}

    @app.get("/api/v1/plugins")
    def plugins_list() -> dict[str, object]:
        return _plugins_payload(list_plugins())

    @app.post("/api/v1/plugins/reload")
    def plugins_reload() -> dict[str, object]:
        return _plugins_payload(load_plugins())

    @app.post("/api/v1/plugins/{plugin_id}/enable")
    def plugins_enable(plugin_id: str, request: dict[str, bool]) -> dict[str, object]:
        try:
            payload = set_plugin_enabled(plugin_id, bool(request.get("enabled", True)))
        except ValueError as exc:
            raise HTTPException(
                status_code=404,
                detail={"ok": False, "code": "plugin_not_found", "message": str(exc)},
            ) from exc
        return {"ok": True, "plugin": payload}

    @app.get("/api/v1/settings")
    def settings_get() -> dict[str, object]:
        return {
            "ok": True,
            "settings": load_settings().model_dump(mode="json"),
            "env": env_overrides(),
            "restart_required": [
                "runtime.host",
                "runtime.port",
                "runtime.max_jobs",
                "runtime.history",
                "paths.ffmpeg",
                "paths.ffprobe",
                "paths.allowed_roots",
                "paths.cache_dir",
                "paths.models_dir",
                "automation.scheduler_interval_seconds",
                "notifications.enabled",
                "notifications.email.enabled",
                "notifications.slack.enabled",
                "notifications.signal.enabled",
                "search.enabled",
                "search.providers",
            ],
        }

    @app.put("/api/v1/settings")
    def settings_put(request: AppSettings) -> dict[str, object]:
        saved = save_settings(request)
        return {"ok": True, "settings": saved.model_dump(mode="json")}

    @app.post("/api/v1/settings/reset")
    def settings_reset() -> dict[str, object]:
        saved = save_settings(AppSettings())
        return {"ok": True, "settings": saved.model_dump(mode="json")}

    @app.get("/api/v1/settings/export")
    def settings_export() -> dict[str, object]:
        return {
            "ok": True,
            "file": "videoflow-settings.json",
            "settings": load_settings().model_dump(mode="json"),
        }

    @app.post("/api/v1/settings/import")
    def settings_import(request: AppSettings) -> dict[str, object]:
        saved = save_settings(request)
        return {"ok": True, "settings": saved.model_dump(mode="json")}
