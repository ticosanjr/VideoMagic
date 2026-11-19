"""Local API route aggregator."""

from __future__ import annotations

from fastapi import FastAPI

from videoflow.api.routes_admin import register_admin_routes
from videoflow.api.routes_assets import register_asset_routes
from videoflow.api.routes_batches import register_batch_routes
from videoflow.api.routes_copilot import register_copilot_routes
from videoflow.api.routes_discovery import register_discovery_routes
from videoflow.api.routes_gpu import register_gpu_routes
from videoflow.api.routes_gpu_worker import register_gpu_worker_routes
from videoflow.api.routes_hilt import register_hilt_routes
from videoflow.api.routes_intelligence import register_intelligence_routes
from videoflow.api.routes_jobs import register_job_routes
from videoflow.api.routes_library import register_library_routes
from videoflow.api.routes_media import register_media_routes
from videoflow.api.routes_outputs import register_output_routes
from videoflow.api.routes_presets import register_preset_routes
from videoflow.api.routes_providers import register_provider_routes
from videoflow.api.routes_publish import register_publish_routes
from videoflow.api.routes_recipes import register_recipe_routes
from videoflow.api.routes_schedules import register_schedule_routes
from videoflow.api.routes_styles import register_style_routes
from videoflow.api.routes_system import register_system_routes
from videoflow.api.routes_timeline import register_timeline_routes
from videoflow.api.routes_workflows import register_workflow_routes
from videoflow.application.jobs import JobManager
from videoflow.engine.batch import BatchManager


def register_routes(
    app: FastAPI,
    jobs: JobManager,
    batches: BatchManager | None = None,
) -> None:
    """Register every local API route domain on the app."""
    batch_manager = batches or BatchManager(jobs)
    app.state.batches = batch_manager

    register_batch_routes(app, batch_manager)
    register_asset_routes(app)
    register_discovery_routes(app)
    register_gpu_routes(app)
    register_gpu_worker_routes(app)
    register_preset_routes(app)
    register_style_routes(app)
    register_workflow_routes(app)
    register_recipe_routes(app, jobs)
    register_system_routes(app)
    register_admin_routes(app)
    register_provider_routes(app)
    register_publish_routes(app, jobs)
    register_library_routes(app)
    register_schedule_routes(app, jobs)
    register_media_routes(app)
    register_copilot_routes(app, jobs)
    register_job_routes(app, jobs)
    register_hilt_routes(app, jobs)
    register_intelligence_routes(app)
    register_output_routes(app, jobs)
    register_timeline_routes(app, jobs)
