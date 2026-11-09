from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace

from videoflow.application import hilt, hilt_channels
from videoflow.application.settings import AppSettings
from videoflow.domain.hilt import HiltQuestion


def _request(tmp_path: Path, channel: str):
    request, token = hilt.create_request(
        tmp_path / "out",
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        questions=[HiltQuestion(id="topic", label="Topic")],
        channels=[channel],
        job_id="job-1",
    )
    return SimpleNamespace(output=tmp_path / "out", job_id="job-1"), request, token


def _settings(channel: str) -> AppSettings:
    settings = AppSettings()
    if channel == "email":
        settings.notifications.email.enabled = True
        settings.notifications.email.imap_host = "imap.example.com"
        settings.notifications.email.imap_user = "user"
    elif channel == "slack":
        settings.notifications.slack.enabled = True
        settings.notifications.slack.mode = "bot"
        settings.notifications.slack.channel = "#videoflow"
    else:
        settings.notifications.signal.enabled = True
        settings.notifications.signal.api_url = "http://127.0.0.1:8080"
        settings.notifications.signal.number = "+15550001"
    return settings


def test_email_poller_dispatches_a_reply(monkeypatch, tmp_path: Path) -> None:
    job, request, _token = _request(tmp_path, "email")
    token = "abcdefghijklmnopqrstuvwx"
    message = EmailMessage()
    message["From"] = "editor@example.com"
    message["Subject"] = f"Re: #{token}"
    message.set_content("topic: corruption")
    message.add_attachment(
        b"# research\n", maintype="text", subtype="markdown", filename="agent.md"
    )
    raw = message.as_bytes()
    calls = {}

    class FakeImap:
        def __init__(self, host, port):
            calls["host"] = host

        def login(self, user, password):
            calls["login"] = user

        def select(self, folder):
            return "OK", [b"1"]

        def search(self, charset, criteria):
            return "OK", [b"1"]

        def fetch(self, number, spec):
            return "OK", [(b"1", raw)]

        def store(self, number, flag, value):
            calls["seen"] = True

        def logout(self):
            calls["logout"] = True

    monkeypatch.setattr(hilt_channels.imaplib, "IMAP4_SSL", FakeImap)
    monkeypatch.setattr(hilt_channels, "load_settings", lambda: _settings("email"))
    monkeypatch.setattr(hilt_channels, "_pending", lambda jobs: [(job, request)])
    monkeypatch.setattr(
        hilt_channels, "_match_request", lambda jobs, token: (job, request)
    )
    replies = []
    monkeypatch.setattr(
        hilt_channels,
        "dispatch_reply",
        lambda jobs, reply: replies.append(reply) or {"ok": True},
    )
    hilt_channels._poll_email(object(), _settings("email"))
    assert replies and replies[0].channel == "email"
    assert replies[0].attachments[0].filename == "agent.md"
    assert calls["seen"] is True


def test_slack_poller_dispatches(monkeypatch, tmp_path: Path) -> None:
    job, request, _token = _request(tmp_path, "slack")
    token = "abcdefghijklmnopqrstuvwx"

    class Response:
        status_code = 200
        content = b"{}"

        def json(self):
            return {
                "ok": True,
                "messages": [{"text": f"#{token}", "user": "U1"}],
            }

    monkeypatch.setattr(hilt_channels.httpx, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(hilt_channels, "load_settings", lambda: _settings("slack"))
    monkeypatch.setattr(hilt_channels, "get_secret", lambda name: "token")
    monkeypatch.setattr(hilt_channels, "_pending", lambda jobs: [(job, request)])
    monkeypatch.setattr(
        hilt_channels, "_match_request", lambda jobs, token: (job, request)
    )
    replies = []
    monkeypatch.setattr(
        hilt_channels, "dispatch_reply", lambda jobs, reply: replies.append(reply)
    )
    hilt_channels._poll_slack(object(), _settings("slack"))
    assert replies and replies[0].channel == "slack"


def test_signal_poller_dispatches_with_attachment(monkeypatch, tmp_path: Path) -> None:
    job, request, _token = _request(tmp_path, "signal")
    token = "abcdefghijklmnopqrstuvwx"
    calls = {"n": 0}

    class Response:
        status_code = 200
        content = b"attachment"

        def json(self):
            return [
                {
                    "envelope": {
                        "sourceNumber": "+15550002",
                        "dataMessage": {
                            "message": f"#{token}",
                            "attachments": [
                                {"id": "att-1", "filename": "patch.wav", "contentType": "audio/wav"}
                            ],
                        },
                    }
                }
            ]

    def fake_get(url, **kwargs):
        calls["n"] += 1
        return Response()

    monkeypatch.setattr(hilt_channels.httpx, "get", fake_get)
    monkeypatch.setattr(hilt_channels, "load_settings", lambda: _settings("signal"))
    monkeypatch.setattr(hilt_channels, "get_secret", lambda name: "")
    monkeypatch.setattr(hilt_channels, "_pending", lambda jobs: [(job, request)])
    monkeypatch.setattr(
        hilt_channels, "_match_request", lambda jobs, token: (job, request)
    )
    replies = []
    monkeypatch.setattr(
        hilt_channels, "dispatch_reply", lambda jobs, reply: replies.append(reply)
    )
    hilt_channels._poll_signal(object(), _settings("signal"))
    assert replies and replies[0].attachments[0].filename == "patch.wav"
    assert calls["n"] >= 2


def test_notification_failure_is_logged(monkeypatch, tmp_path: Path) -> None:
    job, request, token = _request(tmp_path, "email")
    settings = _settings("email")
    settings.notifications.email.enabled = True

    def broken(settings, message):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(hilt_channels, "_send_email", broken)
    results = hilt_channels.notify_request(
        tmp_path / "out", request, token, settings=settings
    )
    assert results[0]["ok"] is False
    assert "smtp down" in results[0]["detail"]


def test_pollers_start_and_stop(monkeypatch) -> None:
    settings = AppSettings()
    settings.notifications.email.enabled = True
    settings.notifications.slack.enabled = True
    settings.notifications.signal.enabled = True
    monkeypatch.setattr(hilt_channels, "load_settings", lambda: settings)
    monkeypatch.setattr(hilt_channels, "_loop", lambda *args, **kwargs: None)
    hilt_channels.start_pollers(object())
    hilt_channels.stop_pollers()
