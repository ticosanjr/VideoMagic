"""Publishing, project templates, brand templates, and config interchange."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from videoflow.application.brand_templates import (
    BrandTemplate,
    apply_brand_options,
    delete_template,
    get_template,
    list_templates,
    save_template,
)
from videoflow.application.jobs import JobManager
from videoflow.application.project_templates import (
    ProjectTemplate,
    export_config,
    import_config,
    sanitize_options,
)
from videoflow.application.project_templates import (
    delete_template as delete_project_template,
)
from videoflow.application.project_templates import (
    get_template as get_project_template,
)
from videoflow.application.project_templates import (
    list_templates as list_project_templates,
)
from videoflow.application.project_templates import (
    save_template as save_project_template,
)
from videoflow.application.publishing import (
    PublishTarget,
    cancel_publish,
    delete_target,
    dispatch_due,
    enqueue_publish,
    list_queue,
    list_targets,
    save_target,
)
from videoflow.application.short_metadata import generate_short_metadata
from videoflow.domain.errors import StateNotReadyError


class PublishTargetRequest(BaseModel):
    description: str = ""
    webhook_url: str = Field(min_length=1)
    secret_name: str = "VIDEOWFLOW_PUBLISH_TOKEN"
    enabled: bool = True


class PublishShortRequest(BaseModel):
    target: str = Field(min_length=1)
    platform: Literal["youtube", "tiktok", "instagram", "linkedin"] = "youtube"
    tone: Literal["engaging", "professional", "educational", "bold"] = "engaging"
    scheduled_at: str | None = None
    extra_hashtags: list[str] = Field(default_factory=list)
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class PublishDispatchRequest(BaseModel):
    allow_external_services: bool = False
    allowed_external_hosts: list[str] = Field(default_factory=list)


class ConfigExportRequest(BaseModel):
    options: dict[str, Any] = Field(default_factory=dict)


class ConfigImportRequest(BaseModel):
    schema_version: int
    options: dict[str, Any] = Field(default_factory=dict)


def register_publish_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register publishing, templates, and config routes."""

    @app.get("/api/v1/publish/targets")
    def publish_targets() -> dict[str, object]:
        return {"ok": True, "targets": list_targets()}

    @app.put("/api/v1/publish/targets/{name}")
    def put_publish_target(name: str, request: PublishTargetRequest) -> dict[str, object]:
        return {
            "ok": True,
            "target": save_target(PublishTarget(name=name, **request.model_dump())),
        }

    @app.delete("/api/v1/publish/targets/{name}")
    def remove_publish_target(name: str) -> dict[str, object]:
        delete_target(name)
        return {"ok": True, "deleted": name}

    @app.get("/api/v1/publish/queue")
    def publish_queue() -> dict[str, object]:
        return {"ok": True, "items": list_queue()}

    @app.post("/api/v1/publish/queue/{item_id}/cancel")
    def cancel_publish_item(item_id: str) -> dict[str, object]:
        return {"ok": True, "item": cancel_publish(item_id)}

    @app.post("/api/v1/publish/dispatch")
    def publish_dispatch(request: PublishDispatchRequest) -> dict[str, object]:
        items = dispatch_due(
            allow_external_services=request.allow_external_services,
            allowed_hosts=tuple(request.allowed_external_hosts),
        )
        return {"ok": True, "items": items}

    @app.post("/api/v1/jobs/{job_id}/shorts/{index}/publish")
    def publish_short(
        job_id: str, index: int, request: PublishShortRequest
    ) -> dict[str, object]:
        job = jobs.get(job_id)
        if job.status != "succeeded" or job.result is None:
            raise StateNotReadyError(
                "The job must succeed before a Short can be published."
            )
        shorts = job.result.get("shorts")
        if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
            raise StateNotReadyError("Short index is out of range.")
        entry = shorts[index]
        if not isinstance(entry, dict) or not entry.get("path"):
            raise StateNotReadyError("Short asset is missing.")
        metadata = generate_short_metadata(
            output=job.output,
            index=index,
            result=job.result,
            platform=request.platform,
            tone=request.tone,
            extra_hashtags=tuple(request.extra_hashtags),
        )
        item = enqueue_publish(
            target_name=request.target,
            asset_path=Path(str(entry["path"])),
            title=str(metadata["title"]),
            description=str(metadata["description"]),
            hashtags=[str(tag) for tag in metadata["hashtags"]],
            platform=request.platform,
            scheduled_at=request.scheduled_at,
            job_id=job_id,
            short_index=index,
        )
        return {"ok": True, "item": item}

    @app.get("/api/v1/project-templates")
    def project_templates() -> dict[str, object]:
        return {"ok": True, "templates": list_project_templates()}

    @app.get("/api/v1/project-templates/{name}")
    def project_template(name: str) -> dict[str, object]:
        return {
            "ok": True,
            "template": get_project_template(name).model_dump(mode="json"),
        }

    @app.put("/api/v1/project-templates/{name}")
    def put_project_template(name: str, template: ProjectTemplate) -> dict[str, object]:
        payload = save_project_template(template.model_copy(update={"name": name}))
        return {"ok": True, "template": payload}

    @app.delete("/api/v1/project-templates/{name}")
    def remove_project_template(name: str) -> dict[str, object]:
        delete_project_template(name)
        return {"ok": True, "deleted": name}

    @app.post("/api/v1/project-templates/{name}/apply")
    def apply_project_template(name: str) -> dict[str, object]:
        options = get_project_template(name).options
        return {"ok": True, "options": sanitize_options(options)}

    @app.post("/api/v1/config/export")
    def config_export(request: ConfigExportRequest) -> dict[str, object]:
        return {"ok": True, "envelope": export_config(request.options)}

    @app.post("/api/v1/config/import")
    def config_import(request: ConfigImportRequest) -> dict[str, object]:
        options = import_config(
            {"schema_version": request.schema_version, "options": request.options}
        )
        return {"ok": True, "options": options}

    @app.get("/api/v1/brand-templates")
    def brand_templates() -> dict[str, object]:
        return {"ok": True, "templates": list_templates()}

    @app.get("/api/v1/brand-templates/{name}")
    def brand_template(name: str) -> dict[str, object]:
        return {"ok": True, "template": get_template(name).model_dump(mode="json")}

    @app.put("/api/v1/brand-templates/{name}")
    def put_brand_template(name: str, template: BrandTemplate) -> dict[str, object]:
        payload = save_template(template.model_copy(update={"name": name}))
        return {"ok": True, "template": payload}

    @app.delete("/api/v1/brand-templates/{name}")
    def remove_brand_template(name: str) -> dict[str, object]:
        delete_template(name)
        return {"ok": True, "deleted": name}

    @app.post("/api/v1/brand-templates/{name}/apply")
    def apply_brand_template(name: str) -> dict[str, object]:
        options = apply_brand_options({}, name)
        return {"ok": True, "options": options}
