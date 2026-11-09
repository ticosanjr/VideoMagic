"""Recipe schedule routes."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from videoflow.application.jobs import JobManager
from videoflow.application.schedules import (
    RecipeSchedule,
    delete_schedule,
    load_schedules,
    run_now,
    upsert_schedule,
)


def register_schedule_routes(app: FastAPI, jobs: JobManager) -> None:
    """Register recipe schedule CRUD and run-now routes."""

    @app.get("/api/v1/schedules")
    def schedules_list() -> dict[str, object]:
        return {
            "ok": True,
            "schedules": [item.model_dump(mode="json") for item in load_schedules()],
        }

    @app.put("/api/v1/schedules/{schedule_id}")
    def schedules_save(schedule_id: str, request: RecipeSchedule) -> dict[str, object]:
        if request.id != schedule_id:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "code": "schedule_id_mismatch", "message": schedule_id},
            )
        saved = upsert_schedule(request)
        return {"ok": True, "schedule": saved.model_dump(mode="json")}

    @app.delete("/api/v1/schedules/{schedule_id}")
    def schedules_delete(schedule_id: str) -> dict[str, object]:
        delete_schedule(schedule_id)
        return {"ok": True, "deleted": schedule_id}

    @app.post("/api/v1/schedules/{schedule_id}/run")
    def schedules_run(schedule_id: str) -> dict[str, object]:
        schedule = run_now(jobs, schedule_id)
        return {"ok": True, "schedule": schedule.model_dump(mode="json")}
