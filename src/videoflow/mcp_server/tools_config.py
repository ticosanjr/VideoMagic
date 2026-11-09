"""MCP configuration, publishing, model, and plugin tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from videoflow.application.backups import scheduled_backup
from videoflow.application.brand_templates import (
    BrandTemplate,
    list_templates,
    save_template,
)
from videoflow.application.capabilities import (
    capability_manifest,
    external_services_allowed,
)
from videoflow.application.models import install_model, list_models, remove_model
from videoflow.application.plugins import (
    list_plugins,
    load_plugins,
    set_plugin_enabled,
)
from videoflow.application.project_templates import (
    ProjectTemplate,
    export_config,
    import_config,
    sanitize_options,
)
from videoflow.application.project_templates import (
    list_templates as list_project_templates,
)
from videoflow.application.project_templates import (
    save_template as save_project_template,
)
from videoflow.application.providers import fallback_manifest, list_providers
from videoflow.application.publishing import (
    PublishTarget,
    enqueue_publish,
)
from videoflow.application.publishing import (
    list_queue as list_publish_queue,
)
from videoflow.application.publishing import (
    list_targets as list_publish_targets,
)
from videoflow.application.publishing import (
    save_target as save_publish_target,
)
from videoflow.application.schedules import (
    RecipeSchedule,
    load_schedules,
    run_now,
    upsert_schedule,
)
from videoflow.domain.errors import StateNotReadyError, VideoFlowError
from videoflow.mcp_server.context import ToolContext, error


def register_config_tools(register: Any, ctx: ToolContext) -> None:
    """Register publishing, template, model, plugin, and backup tools."""

    manager = ctx.manager
    last = ctx.last

    @register
    def videoflow_list_publish_targets() -> dict[str, object]:
        """List configured webhook publish targets."""

        return {"ok": True, "targets": list_publish_targets()}

    @register
    def videoflow_save_publish_target(
        name: str,
        webhook_url: str,
        description: str = "",
        secret_name: str = "VIDEOWFLOW_PUBLISH_TOKEN",
        enabled: bool = True,
    ) -> dict[str, object]:
        """Save a webhook publishing target."""

        return {
            "ok": True,
            "target": save_publish_target(
                PublishTarget(
                    name=name,
                    webhook_url=webhook_url,
                    description=description,
                    secret_name=secret_name,
                    enabled=enabled,
                )
            ),
        }

    @register
    def videoflow_list_publish_queue() -> dict[str, object]:
        """List scheduled or completed publishing items."""

        return {"ok": True, "items": list_publish_queue()}

    @register
    def videoflow_schedule_short(
        index: int,
        target: str,
        platform: str = "youtube",
        tone: str = "engaging",
        scheduled_at: str | None = None,
    ) -> dict[str, object]:
        """Generate metadata and schedule one Short for a webhook target."""

        job_id = last.get("job_id")
        if not isinstance(job_id, str):
            return error("job_required", "Run a recipe with videoflow_run_recipe first.")
        try:
            job = manager.get(job_id)
            if job.status != "succeeded" or job.result is None:
                raise StateNotReadyError("The job must succeed first.")
            shorts = job.result.get("shorts")
            if not isinstance(shorts, list) or index < 0 or index >= len(shorts):
                raise StateNotReadyError("Short index is out of range.")
            entry = shorts[index]
            if not isinstance(entry, dict) or not entry.get("path"):
                raise StateNotReadyError("Short asset is missing.")
            from videoflow.application.short_metadata import generate_short_metadata

            metadata = generate_short_metadata(
                output=job.output,
                index=index,
                result=job.result,
                platform=platform,
                tone=tone,
            )
            item = enqueue_publish(
                target_name=target,
                asset_path=Path(str(entry["path"])),
                title=str(metadata["title"]),
                description=str(metadata["description"]),
                hashtags=[str(tag) for tag in metadata["hashtags"]],
                platform=platform,
                scheduled_at=scheduled_at,
                job_id=job_id,
                short_index=index,
            )
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "item": item}

    @register
    def videoflow_list_project_templates() -> dict[str, object]:
        """List saved project configuration templates."""

        return {"ok": True, "templates": list_project_templates()}

    @register
    def videoflow_save_project_template(
        name: str, template: dict[str, object]
    ) -> dict[str, object]:
        """Save a flat job configuration template."""

        try:
            payload = ProjectTemplate.model_validate({**template, "name": name})
            return {"ok": True, "template": save_project_template(payload)}
        except VideoFlowError as exc:
            return exc.to_dict()
        except ValueError as exc:
            return error("invalid_template", str(exc))

    @register
    def videoflow_export_config(options: dict[str, object]) -> dict[str, object]:
        """Return a versioned, sanitized configuration envelope."""

        return {"ok": True, "envelope": export_config(options)}

    @register
    def videoflow_import_config(
        schema_version: int, options: dict[str, object]
    ) -> dict[str, object]:
        """Validate and import a configuration envelope."""

        try:
            clean = import_config({"schema_version": schema_version, "options": options})
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "options": sanitize_options(clean)}

    @register
    def videoflow_list_brand_templates() -> dict[str, object]:
        """List saved brand templates."""

        return {"ok": True, "templates": list_templates()}

    @register
    def videoflow_save_brand_template(
        name: str, template: dict[str, object]
    ) -> dict[str, object]:
        """Save a brand template JSON object under a name."""

        try:
            payload = BrandTemplate.model_validate({**template, "name": name})
            return {"ok": True, "template": save_template(payload)}
        except VideoFlowError as exc:
            return exc.to_dict()
        except ValueError as exc:
            return error("invalid_template", str(exc))

    @register
    def videoflow_list_capabilities(
        allow_external_services: bool = False,
    ) -> dict[str, object]:
        """List feature availability and whether external providers are allowed."""

        return {
            "ok": True,
            "external_services_allowed": external_services_allowed(
                allow_external_services
            ),
            "capabilities": capability_manifest(
                allow_external_services=allow_external_services
            ),
        }

    @register
    def videoflow_list_models(
        limit: int = 100, offset: int = 0
    ) -> dict[str, object]:
        """List optional local models and whether they are installed."""

        items = list_models()
        start = max(0, offset)
        page = items[start : start + max(1, min(limit, 1000))]
        return {"ok": True, "models": page, "total": len(items)}

    @register
    def videoflow_install_model(
        model_id: str, allow_external_services: bool = True
    ) -> dict[str, object]:
        """Download and verify one optional local model."""

        try:
            return {
                "ok": True,
                "model": install_model(
                    model_id, allow_network=allow_external_services
                ),
            }
        except VideoFlowError as exc:
            return exc.to_dict()

    @register
    def videoflow_remove_model(model_id: str) -> dict[str, object]:
        """Remove one downloaded model, freeing local disk space."""

        try:
            remove_model(model_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "removed": model_id}

    @register
    def videoflow_list_providers() -> dict[str, object]:
        """List configured providers and fallback chains."""

        return {
            "ok": True,
            "providers": list_providers(),
            "fallbacks": fallback_manifest(),
        }

    @register
    def videoflow_list_schedules() -> dict[str, object]:
        """List recipe schedules and watch folders."""

        return {
            "ok": True,
            "schedules": [item.model_dump(mode="json") for item in load_schedules()],
        }

    @register
    def videoflow_save_schedule(schedule: dict[str, object]) -> dict[str, object]:
        """Create or replace a recipe schedule."""

        try:
            saved = upsert_schedule(RecipeSchedule.model_validate(schedule))
        except (ValueError, VideoFlowError) as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "schedule": saved.model_dump(mode="json")}

    @register
    def videoflow_run_schedule(schedule_id: str) -> dict[str, object]:
        """Run a schedule immediately."""

        try:
            schedule = run_now(manager, schedule_id)
        except VideoFlowError as exc:
            return exc.to_dict()
        return {"ok": True, "schedule": schedule.model_dump(mode="json")}

    @register
    def videoflow_list_plugins(
        limit: int = 100, offset: int = 0
    ) -> dict[str, object]:
        """List local plugin manifests and sandbox status."""

        items = list_plugins()
        start = max(0, offset)
        page = items[start : start + max(1, min(limit, 1000))]
        return {"ok": True, "plugins": page, "total": len(items)}

    @register
    def videoflow_reload_plugins() -> dict[str, object]:
        """Reload every enabled plugin."""

        return {"ok": True, "plugins": load_plugins()}

    @register
    def videoflow_set_plugin_enabled(
        plugin_id: str, enabled: bool
    ) -> dict[str, object]:
        """Enable or disable a plugin."""

        try:
            return {"ok": True, "plugin": set_plugin_enabled(plugin_id, enabled)}
        except ValueError as exc:
            return error("plugin_not_found", str(exc))

    @register
    def videoflow_create_backup() -> dict[str, object]:
        """Create a timestamped SQLite backup and prune old snapshots."""

        try:
            path = scheduled_backup()
        except Exception as exc:
            return error("backup_failed", str(exc))
        return {"ok": True, "backup": str(path)}

    @register
    def videoflow_cost_metrics() -> dict[str, object]:
        """Return token usage and estimated LLM cost."""

        from videoflow.application.cost import snapshot

        return {"ok": True, "usage": snapshot()}
