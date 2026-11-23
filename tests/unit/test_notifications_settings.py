"""Notification defaults, gating, and the reduced event set."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application import hilt
from videoflow.application import settings as settings_module
from videoflow.application.settings import AppSettings, NotificationSettings
from videoflow.domain.hilt import HiltRequest


def _request() -> HiltRequest:
    return HiltRequest(
        interaction_id="hilt-ask-brief",
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        description="Answer to continue.",
    )


def _fake_desktop(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.delenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", raising=False)
    monkeypatch.delenv("VIDEOWFLOW_NOTIFICATIONS", raising=False)
    monkeypatch.setattr(hilt.sys, "platform", "linux")
    monkeypatch.setattr(hilt.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        hilt.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command),
    )
    return calls


def _enabled_settings(**updates: object) -> AppSettings:
    settings = AppSettings()
    settings.notifications.enabled = True
    settings.notifications.local.enabled = True
    settings.notifications.local.desktop = True
    settings.notifications.desktop_level = "required"
    for key, value in updates.items():
        setattr(settings.notifications, key, value)
    return settings


def test_notification_defaults_are_silent() -> None:
    config = NotificationSettings()
    assert config.enabled is False
    assert config.ui_level == "off"
    assert config.desktop_level == "off"
    assert config.default_channels == []
    assert config.local.enabled is False
    assert config.local.desktop is False
    assert config.notify_hitl is True
    assert config.notify_job_failed is True
    assert config.notify_job_finished is False
    assert config.notify_job_cancelled is False
    assert config.notify_warnings is False
    assert config.notify_system is False


def test_legacy_levels_are_mapped() -> None:
    assert NotificationSettings(ui_level="minimal").ui_level == "required"
    assert NotificationSettings(ui_level="standard").ui_level == "important"
    assert NotificationSettings(ui_level="verbose").ui_level == "all"
    assert NotificationSettings(desktop_level="minimal").desktop_level == "required"
    assert NotificationSettings._legacy_level(1) == 1


def test_env_off_overrides_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _enabled_settings()
    monkeypatch.setenv("VIDEOWFLOW_NOTIFICATIONS", "off")
    assert hilt._notifications_enabled(settings) is False
    monkeypatch.setenv("VIDEOWFLOW_NOTIFICATIONS", "1")
    assert hilt._notifications_enabled(settings) is True


def test_notify_local_writes_nothing_by_default(tmp_path: Path) -> None:
    hilt._notify_local(tmp_path, _request(), settings=AppSettings())
    assert not (tmp_path / "notifications.jsonl").exists()
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    payload = json.loads(events[-1])
    assert payload["event"] == "notified"
    assert payload["detail"] == {"channel": "local", "delivered": False}


def test_notify_local_writes_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_desktop(monkeypatch)
    hilt._notify_local(tmp_path, _request(), settings=_enabled_settings())
    assert (tmp_path / "notifications.jsonl").is_file()
    assert calls and calls[0][0].endswith("notify-send")


@pytest.mark.parametrize(
    ("level", "category", "expected"),
    [
        ("off", "hilt", False),
        ("required", "hilt", True),
        ("required", "job_failed", False),
        ("important", "job_failed", True),
        ("important", "job_finished", False),
        ("all", "job_finished", True),
    ],
)
def test_desktop_level_filtering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    level: str,
    category: str,
    expected: bool,
) -> None:
    calls = _fake_desktop(monkeypatch)
    settings = _enabled_settings(desktop_level=level)
    # The local log must exist so the level, not the local flag, decides.
    assert settings.notifications.local.enabled is True
    hilt._desktop_notify("Title", "Body", category=category, settings=settings)
    assert bool(calls) is expected


def test_hitl_flag_disables_local_delivery(tmp_path: Path) -> None:
    settings = _enabled_settings(notify_hitl=False)
    hilt._notify_local(tmp_path, _request(), settings=settings)
    assert not (tmp_path / "notifications.jsonl").exists()


def test_test_local_channel_forces_one_popup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_desktop(monkeypatch)
    result = hilt.test_local_channel("Test")
    assert result["ok"] is True
    assert calls and calls[0][0].endswith("notify-send")


def test_settings_file_accepts_legacy_notification_levels(tmp_path: Path) -> None:
    settings = AppSettings()
    payload = settings.model_dump(mode="json")
    payload["notifications"]["ui_level"] = "minimal"
    payload["notifications"]["desktop_level"] = "verbose"
    path = settings_module.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = settings_module.load_settings()
    assert loaded.notifications.ui_level == "required"
    assert loaded.notifications.desktop_level == "all"


def test_notification_helpers_survive_broken_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def broken() -> AppSettings:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(hilt, "_notifications_enabled", lambda settings=None: True)
    monkeypatch.setattr(hilt, "load_settings", broken)
    hilt._desktop_notify("Title", "Body")
    hilt._notify_local(tmp_path, _request())
    assert not (tmp_path / "notifications.jsonl").exists()


def test_desktop_notify_respects_local_and_hitl_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake_desktop(monkeypatch)

    settings = _enabled_settings()
    settings.notifications.local.enabled = False
    hilt._desktop_notify("Title", "Body", settings=settings)
    assert calls == []

    settings = _enabled_settings()
    settings.notifications.local.desktop = False
    hilt._desktop_notify("Title", "Body", settings=settings)
    assert calls == []

    settings = _enabled_settings(notify_hitl=False)
    hilt._desktop_notify("Title", "Body", settings=settings)
    assert calls == []


def test_notify_local_logs_a_write_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("VIDEOWFLOW_NOTIFICATIONS", raising=False)
    marker = tmp_path / "not-a-directory"
    marker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        hilt,
        "_notifications_path",
        lambda directory: marker / "notifications.jsonl",
    )
    hilt._notify_local(tmp_path, _request(), settings=_enabled_settings())
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(events[-1])["detail"]["delivered"] is True
