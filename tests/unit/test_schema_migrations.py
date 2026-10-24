"""Versioned migration helpers for settings, providers, schedules, and plugins."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.application import schema_migrations
from videoflow.domain.errors import VideoFlowError


def test_settings_gain_defaults_and_stay_idempotent() -> None:
    once = schema_migrations.migrate_settings({"ui": {"theme": "light"}})
    twice = schema_migrations.migrate_settings(once)

    assert once["schema_version"] == 1
    assert once["runtime"] == {}
    assert once["automation"] == {}
    assert twice == once


def test_providers_schedules_and_plugins_gain_defaults() -> None:
    providers = schema_migrations.migrate_providers({"providers": [{"id": "p"}]})
    assert providers["fallbacks"] == {}
    schedule = schema_migrations.migrate_schedule({"id": "s"})
    assert schedule["max_retries"] == 5
    plugin = schema_migrations.migrate_plugin_manifest({"id": "p"})
    assert plugin["permissions"] == []
    assert plugin["enabled"] is True


def test_a_newer_schema_is_rejected() -> None:
    with pytest.raises(VideoFlowError):
        schema_migrations.migrate_settings({"schema_version": 9})
    with pytest.raises(VideoFlowError):
        schema_migrations.migrate_plugin_manifest({"schema_version": 9})


def test_settings_load_accepts_a_legacy_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from videoflow.application.settings import load_settings

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    (tmp_path / "settings.json").write_text(
        '{"schema_version": 1, "ui": {"theme": "light"}}', encoding="utf-8"
    )

    settings = load_settings()

    assert settings.ui.theme == "light"
    assert settings.runtime.locale
