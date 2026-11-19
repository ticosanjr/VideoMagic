"""Local MCP control-plane API route aggregator."""

from __future__ import annotations

from fastapi import FastAPI

from videoflow.api.routes_admin import register_admin_routes
from videoflow.api.routes_discovery import register_discovery_routes
from videoflow.api.routes_gpu import register_gpu_routes
from videoflow.api.routes_gpu_worker import register_gpu_worker_routes
from videoflow.api.routes_hilt import register_hilt_routes
from videoflow.api.routes_intelligence import register_intelligence_routes
from videoflow.api.routes_jobs import register_job_routes
from videoflow.api.routes_outputs import register_output_routes
from videoflow.api.routes_providers import register_provider_routes
from videoflow.api.routes_system import register_system_routes
from videoflow.application.jobs import JobManager


def register_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register the configuration and observability routes used by MCP."""

    register_discovery_routes(app)
    register_gpu_routes(app)
    register_gpu_worker_routes(app)
    register_system_routes(app)
    register_admin_routes(app)
    register_provider_routes(app)
    register_job_routes(app, jobs)
    register_hilt_routes(app, jobs)
    register_intelligence_routes(app)
    register_output_routes(app, jobs)
