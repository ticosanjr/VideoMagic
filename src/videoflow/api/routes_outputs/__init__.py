"""Job output routes split by domain."""

from __future__ import annotations

from fastapi import FastAPI

from videoflow.api.routes_outputs.artifacts import register_artifact_routes
from videoflow.api.routes_outputs.deps import *  # noqa: F401,F403
from videoflow.api.routes_outputs.exports import register_export_routes
from videoflow.api.routes_outputs.models import *  # noqa: F401,F403
from videoflow.api.routes_outputs.previews import register_preview_routes
from videoflow.api.routes_outputs.qa import register_qa_routes
from videoflow.api.routes_outputs.shorts import register_short_routes
from videoflow.application.jobs import JobManager


def register_output_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register all job output routes."""

    register_short_routes(app, jobs)
    register_preview_routes(app, jobs)
    register_export_routes(app, jobs)
    register_qa_routes(app, jobs)
    register_artifact_routes(app, jobs)


__all__ = ["register_output_routes"]
