from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from videoflow.application import hilt, hilt_channels
from videoflow.application.hilt_channels import outbound as outbound_module
from videoflow.application.hilt_channels import webhooks as webhooks_module
from videoflow.application.settings import AppSettings
from videoflow.domain.hilt import HiltQuestion


def _settings() -> AppSettings:
    settings = AppSettings()
    settings.notifications.email.enabled = True
    settings.notifications.email.smtp_host = "smtp.example.com"
    settings.notifications.email.from_address = "from@example.com"
    settings.notifications.email.to_addresses = ["to@example.com"]
    settings.notifications.slack.enabled = True
    settings.notifications.slack.mode = "webhook"
    settings.notifications.slack.channel = "#videoflow"
    settings.notifications.signal.enabled = True
    settings.notifications.signal.api_url = "http://127.0.0.1:8080"
    settings.notifications.signal.number = "+15550001"
    settings.notifications.signal.recipients = ["+15550002"]
    return settings


def test_email_send_contract(monkeypatch) -> None:
    events = {}

    class FakeSmtp:
        def __init__(self, host, port, timeout=20):
            events["host"] = host

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            events["tls"] = True

        def login(self, user, password):
            events["login"] = user

        def send_message(self, message):
            events["subject"] = message["Subject"]

    monkeypatch.setattr(outbound_module.smtplib, "SMTP", FakeSmtp)
    settings = _settings()
    settings.notifications.email.smtp_user = "user"
    message = hilt_channels.OutboundMessage(
        title="Review",
        body="Body",
        interaction_id="i",
        job_id="j",
        token="token",
        url="http://localhost",
        expires_at="",
    )
    detail = outbound_module._send_email(settings, message)
    assert "sent" in detail
    assert events["host"] == "smtp.example.com"
    assert "Review" in events["subject"]


def test_slack_webhook_and_bot(monkeypatch) -> None:
    monkeypatch.setattr(
        outbound_module,
        "get_secret",
        lambda name: "https://hooks.example/slack" if name == "webhook" else "bot",
    )

    def fake_post(url, **kwargs):
        return SimpleNamespace(
            status_code=200,
            content=b'{"ok": true}',
            json=lambda: {"ok": True},
        )

    monkeypatch.setattr(outbound_module.httpx, "post", fake_post)
    settings = _settings()
    message = hilt_channels.OutboundMessage(
        title="Review", body="Body", interaction_id="i", job_id="j",
        token="token", url="http://localhost", expires_at=""
    )
    assert "webhook" in outbound_module._send_slack(settings, message)
    settings.notifications.slack.mode = "bot"
    assert "chat.postMessage" in outbound_module._send_slack(settings, message)


def test_ingest_slack_event_and_email_payload(monkeypatch) -> None:
    settings = AppSettings()
    monkeypatch.setattr(webhooks_module, "load_settings", lambda: settings)
    monkeypatch.setattr(
        webhooks_module,
        "dispatch_reply",
        lambda jobs, reply: {"ok": True, "channel": reply.channel, "token": reply.token},
    )
    token = "abcdefghijklmnopqrstuvwx"
    slack = hilt_channels.ingest_slack_event(
        {
            "type": "event_callback",
            "event": {
                "type": "message",
                "text": f"# {token}",
                "user": "U1",
            },
        },
        b"{}",
        {},
        object(),
    )
    assert slack["ok"] is True
    email = hilt_channels.ingest_email_payload(
        {
            "from": "editor@example.com",
            "subject": f"Re: #{token}",
            "text": "topic: x",
            "attachments": [],
        },
        b"{}",
        {},
        object(),
    )
    assert email["ok"] is True


def test_notify_request_logs_external_channels(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, token = hilt.create_request(
        output,
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        questions=[HiltQuestion(id="topic", label="Topic")],
        channels=["email", "slack"],
        job_id="job-1",
    )
    monkeypatch.setattr(
        outbound_module,
        "_send_email",
        lambda settings, message: "email ok",
    )
    monkeypatch.setattr(
        outbound_module,
        "_send_slack",
        lambda settings, message: "slack ok",
    )
    results = hilt_channels.notify_request(
        output, request, token, settings=_settings()
    )
    assert [item["channel"] for item in results] == ["email", "slack"]
    assert all(item["ok"] for item in results)
    assert (output / "hilt" / request.interaction_id / "notifications.jsonl").is_file()
