"""OpenAPI contract polish: error envelope, examples, and write preconditions."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["ok", "code", "message"],
    "properties": {
        "ok": {"type": "boolean", "const": False},
        "code": {
            "type": "string",
            "description": "Stable machine code. See docs/errors.md.",
            "examples": ["path_not_allowed", "job_not_found", "precondition_failed"],
        },
        "message": {
            "type": "string",
            "description": "Human message with the next action. Never contains secrets.",
        },
        "details": {
            "type": "object",
            "additionalProperties": True,
            "description": "Optional structured context, for example a fresh ETag.",
        },
    },
}

ERROR_RESPONSE: dict[str, Any] = {
    "description": "Actionable failure envelope.",
    "content": {
        "application/json": {
            "schema": {"$ref": "#/components/schemas/ErrorEnvelope"},
            "examples": {
                "stale_timeline": {
                    "value": {
                        "detail": {
                            "ok": False,
                            "code": "precondition_failed",
                            "message": (
                                "The timeline changed since it was loaded. Refresh "
                                "the timeline and reapply the edit."
                            ),
                            "details": {"etag": '"timeline-7"'},
                        }
                    }
                },
                "job_missing": {
                    "value": {
                        "detail": {
                            "ok": False,
                            "code": "job_not_found",
                            "message": "Unknown job: 00000000. Refresh Runs.",
                        }
                    }
                },
            },
        }
    },
}

EXAMPLES: dict[tuple[str, str], dict[str, Any]] = {
    ("get", "/api/v1/jobs/{job_id}/timeline"): {
        "description": (
            "Canonical timeline. Send the returned revision to edits via If-Match. "
            "Returns 304 when If-None-Match still matches."
        ),
        "responses": {
            "200": {
                "headers": {
                    "ETag": {
                        "schema": {"type": "string"},
                        "description": 'Timeline revision, for example "timeline-7".',
                    }
                },
                "content": {
                    "application/json": {
                        "example": {
                            "ok": True,
                            "job_id": "0a4f0e8a",
                            "revision": 7,
                            "can_undo": True,
                            "can_redo": False,
                            "fps": 30.0,
                            "duration_sec": 42.5,
                            "video": [
                                {
                                    "id": "v1",
                                    "start_sec": 0.0,
                                    "end_sec": 3.2,
                                    "source_in_frame": 0,
                                    "source_out_frame": 96,
                                }
                            ],
                            "audio": [],
                            "markers": [],
                        }
                    }
                },
            },
            "304": {"description": "Timeline unchanged for the supplied If-None-Match."},
            "412": ERROR_RESPONSE,
        },
    },
    ("patch", "/api/v1/jobs/{job_id}/timeline"): {
        "description": (
            "Apply one timeline edit. Send If-Match with the last revision; a stale "
            "value fails with 412 and a fresh ETag before anything is written."
        ),
        "parameters": [
            {
                "name": "If-Match",
                "in": "header",
                "required": False,
                "schema": {"type": "string"},
                "description": 'Last known ETag, for example "timeline-7".',
            }
        ],
        "responses": {"412": ERROR_RESPONSE},
    },
    ("post", "/api/v1/recipes/run"): {
        "description": (
            "Queue a run. Poll GET /api/v1/jobs/{job_id} or use the SSE stream. "
            "Use Idempotency-Key to avoid duplicate runs."
        ),
        "responses": {
            "202": {
                "content": {
                    "application/json": {
                        "example": {
                            "ok": True,
                            "job": {
                                "job_id": "4d2c1b0a",
                                "status": "queued",
                                "stage": "queued",
                                "progress": 0,
                            },
                        }
                    }
                }
            },
            "429": {
                "description": "Queue or budget limit reached.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorEnvelope"},
                        "example": {
                            "detail": {
                                "ok": False,
                                "code": "job_queue_full",
                                "message": "The queue is full. Wait or cancel a run.",
                            }
                        },
                    }
                },
            },
        },
    },
    ("get", "/api/v1/jobs/{job_id}/logs"): {
        "description": "Filter by step module and level. `download=true` returns text.",
        "parameters": [
            {"name": "module", "in": "query", "schema": {"type": "string"}},
            {
                "name": "level",
                "in": "query",
                "schema": {"type": "string", "enum": ["debug", "info", "warning", "error"]},
            },
            {
                "name": "limit",
                "in": "query",
                "schema": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        ],
    },
    ("post", "/api/v1/projects"): {
        "description": "Create a local project. Deleting it never deletes media.",
        "responses": {
            "201": {
                "content": {
                    "application/json": {
                        "example": {
                            "ok": True,
                            "project": {
                                "id": "project-8f21c0d4a1",
                                "name": "Interview",
                                "source": "/media/source.mp4",
                                "output": "/media/output",
                                "created_at": "2026-01-01T10:00:00+00:00",
                                "updated_at": "2026-01-01T10:00:00+00:00",
                                "last_job_id": "",
                            },
                        }
                    }
                }
            }
        },
    },
}

COMMON_ERRORS = {
    "400": ERROR_RESPONSE,
    "403": ERROR_RESPONSE,
    "404": ERROR_RESPONSE,
    "409": ERROR_RESPONSE,
    "412": ERROR_RESPONSE,
    "422": ERROR_RESPONSE,
    "429": ERROR_RESPONSE,
    "500": ERROR_RESPONSE,
}


def install_openapi(app: FastAPI) -> None:
    """Replace the generated schema with one that documents the real contract."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=(
                app.description
                + "\n\nLocal-only API. Bind is loopback. Errors use the "
                "`detail` envelope with a stable `code`. See docs/errors.md."
            ),
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components["ErrorEnvelope"] = ERROR_SCHEMA
        schema["info"]["x-api-version"] = app.version
        schema["info"]["x-contract"] = "docs/api.md"
        for path, methods in schema.get("paths", {}).items():
            for method, operation in methods.items():
                if not isinstance(operation, dict):
                    continue
                example = EXAMPLES.get((method, path))
                if example:
                    for key, value in example.items():
                        if key == "responses":
                            operation.setdefault("responses", {}).update(value)
                        elif key == "parameters":
                            operation.setdefault("parameters", []).extend(value)
                        else:
                            operation[key] = value
                if method in {"post", "put", "patch", "delete"}:
                    responses = operation.setdefault("responses", {})
                    for code, payload in COMMON_ERRORS.items():
                        responses.setdefault(code, payload)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
