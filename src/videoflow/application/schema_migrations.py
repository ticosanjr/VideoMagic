"""Version gates for the remaining persisted JSON shapes.

ProjectState and recipes already have dedicated migrations. Settings, providers,
schedules, and plugin manifests get the same contract here: refuse a newer
schema, fill defaults, and stay idempotent.
"""

from __future__ import annotations

from typing import Any

from videoflow.domain.errors import VideoFlowError

SETTINGS_VERSION = 1
PROVIDERS_VERSION = 1
SCHEDULE_VERSION = 1
PLUGIN_VERSION = 1


class SchemaTooNewError(VideoFlowError):
    code = "schema_too_new"


def _migrate(
    payload: dict[str, Any], target: int, kind: str
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SchemaTooNewError(f"{kind} root must be a JSON object")
    version = int(payload.get("schema_version", 1))
    if version > target:
        raise SchemaTooNewError(
            f"{kind} schema_version {version} is newer than {target}"
        )
    migrated = dict(payload)
    migrated["schema_version"] = target
    return migrated


def migrate_settings(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = _migrate(payload, SETTINGS_VERSION, "settings")
    migrated.setdefault("runtime", {})
    migrated.setdefault("ui", {})
    migrated.setdefault("automation", {})
    migrated.setdefault("models", {})
    return migrated


def migrate_providers(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = _migrate(payload, PROVIDERS_VERSION, "providers")
    migrated.setdefault("providers", [])
    migrated.setdefault("fallbacks", {})
    migrated.setdefault("defaults", {})
    return migrated


def migrate_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = _migrate(payload, SCHEDULE_VERSION, "schedule")
    migrated.setdefault("attempts", 0)
    migrated.setdefault("max_retries", 5)
    return migrated


def migrate_plugin_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = _migrate(payload, PLUGIN_VERSION, "plugin manifest")
    migrated.setdefault("permissions", [])
    migrated.setdefault("provides", [])
    migrated.setdefault("enabled", True)
    return migrated
