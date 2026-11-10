from __future__ import annotations

import base64
import hashlib
import hmac
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import hilt, hilt_channels
from videoflow.application.hilt_channels import outbound as outbound_module
from videoflow.application.hilt_channels import pollers as pollers_module
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
    settings.notifications.slack.webhook_secret = "webhook"
    settings.notifications.slack.channel = "#videoflow"
    settings.notifications.signal.enabled = True
    settings.notifications.signal.api_url = "http://127.0.0.1:8080"
    settings.notifications.signal.number = "+15550001"
    settings.notifications.signal.recipients = ["+15550002"]
    return settings


def _message() -> hilt_channels.OutboundMessage:
    return hilt_channels.OutboundMessage(
        title="Review",
        body="Body",
        interaction_id="i",
        job_id="j",
        token="token",
        url="http://localhost",
        expires_at="",
    )


class _Response:
    def __init__(self, status_code=200, payload=None, content=b"{}") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content

    def json(self):
        return self._payload


def test_slack_signature_rejects_bad_inputs_and_accepts_valid() -> None:
    body = b"{}"
    timestamp = str(int(time.time()))
    secret = "secret"
    base = b"v0:" + timestamp.encode() + b":" + body
    signature = "v0=" + hmac.new(
        secret.encode(), base, hashlib.sha256
    ).hexdigest()
    assert webhooks_module.verify_slack_signature(body, timestamp, signature, secret)
    assert not webhooks_module.verify_slack_signature(body, "", signature, secret)
    assert not webhooks_module.verify_slack_signature(body, timestamp, "", secret)
    assert not webhooks_module.verify_slack_signature(body, "old", signature, secret)
    assert not webhooks_module.verify_slack_signature(body, "not-a-number", signature, secret)


def test_slack_attachments_downloads_and_skips(monkeypatch) -> None:
    monkeypatch.setattr(webhooks_module, "get_secret", lambda name: "bot")
    monkeypatch.setattr(
        webhooks_module.httpx,
        "get",
        lambda url, **kwargs: _Response(200, content=b"file")
        if "ok" in url
        else _Response(404),
    )
    files = [
        "not a dict",
        {"url_private_download": "https://slack.example/ok"},
        {"url_private": "https://slack.example/bad"},
        {},
    ]
    attachments = webhooks_module._slack_attachments(files, _settings())
    assert len(attachments) == 1
    assert attachments[0].data == b"file"


def test_ingest_slack_event_branches(monkeypatch) -> None:
    settings = _settings()
    settings.notifications.slack.signing_secret = "secret"
    monkeypatch.setattr(webhooks_module, "load_settings", lambda: settings)
    monkeypatch.setattr(webhooks_module, "get_secret", lambda name: "secret")
    calls = []
    monkeypatch.setattr(
        webhooks_module,
        "dispatch_reply",
        lambda jobs, reply: calls.append(reply) or {"ok": True},
    )

    assert webhooks_module.ingest_slack_event({}, b"{}", {}, object())["code"] == (
        "invalid_signature"
    )
    settings.notifications.slack.signing_secret = ""
    monkeypatch.setattr(webhooks_module, "get_secret", lambda name: "")
    assert webhooks_module.ingest_slack_event(
        {"type": "url_verification", "challenge": "c"}, b"{}", {}, object()
    )["challenge"] == "c"
    assert webhooks_module.ingest_slack_event(
        {"type": "event_callback", "event": {"type": "reaction"}},
        b"{}",
        {},
        object(),
    )["ignored"] is True
    assert webhooks_module.ingest_slack_event(
        {"type": "event_callback", "event": {"type": "message", "bot_id": "b"}},
        b"{}",
        {},
        object(),
    )["ignored"] is True
    assert webhooks_module.ingest_slack_event(
        {"type": "event_callback", "event": {"type": "message", "text": "no token"}},
        b"{}",
        {},
        object(),
    )["ignored"] is True

    settings.notifications.slack.allowed_users = ["U2"]
    assert webhooks_module.ingest_slack_event(
        {
            "type": "event_callback",
            "event": {
                "type": "message",
                "text": "#abcdefghijklmnopqrstuvwx",
                "user": "U1",
            },
        },
        b"{}",
        {},
        object(),
    )["code"] == "sender_not_allowed"

    settings.notifications.slack.allowed_users = []
    result = webhooks_module.ingest_slack_event(
        {
            "type": "event_callback",
            "event": {
                "type": "message",
                "text": "#abcdefghijklmnopqrstuvwx",
                "user": "U1",
            },
        },
        b"{}",
        {},
        object(),
    )
    assert result["ok"] is True
    assert calls[0].channel == "slack"


def test_ingest_email_payload_branches(monkeypatch) -> None:
    settings = _settings()
    monkeypatch.setattr(webhooks_module, "load_settings", lambda: settings)
    calls = []
    monkeypatch.setattr(
        webhooks_module,
        "dispatch_reply",
        lambda jobs, reply: calls.append(reply) or {"ok": True},
    )
    token = "abcdefghijklmnopqrstuvwx"

    monkeypatch.setattr(
        webhooks_module, "get_secret", lambda name: "secret" if "EMAIL" in name else ""
    )
    assert webhooks_module.ingest_email_payload({}, b"{}", {}, object())["code"] == (
        "invalid_signature"
    )
    monkeypatch.setattr(webhooks_module, "get_secret", lambda name: "")

    settings.notifications.email.allowed_senders = ["boss@example.com"]
    assert webhooks_module.ingest_email_payload(
        {"from": "other@example.com"}, b"{}", {}, object()
    )["code"] == "sender_not_allowed"

    settings.notifications.email.allowed_senders = []
    assert webhooks_module.ingest_email_payload(
        {"from": "other@example.com", "text": "no token"}, b"{}", {}, object()
    )["ignored"] is True

    encoded = base64.b64encode(b"data").decode()
    result = webhooks_module.ingest_email_payload(
        {
            "from": "other@example.com",
            "subject": f"#{token}",
            "text": "topic: x",
            "attachments": [
                {"content_base64": "not base64"},
                {"content_base64": encoded, "filename": "a.bin"},
            ],
        },
        b"{}",
        {},
        object(),
    )
    assert result["ok"] is True
    assert calls[0].attachments[0].filename == "a.bin"


def test_outbound_error_branches(monkeypatch) -> None:
    settings = _settings()
    message = _message()

    settings.notifications.email.enabled = False
    with pytest.raises(RuntimeError, match="disabled"):
        outbound_module._send_email(settings, message)
    settings.notifications.email.enabled = True
    settings.notifications.email.smtp_host = ""
    with pytest.raises(RuntimeError, match="required"):
        outbound_module._send_email(settings, message)

    settings.notifications.slack.enabled = False
    with pytest.raises(RuntimeError, match="disabled"):
        outbound_module._send_slack(settings, message)
    settings.notifications.slack.enabled = True
    monkeypatch.setattr(outbound_module, "get_secret", lambda name: "")
    with pytest.raises(RuntimeError, match="Missing Slack webhook"):
        outbound_module._send_slack(settings, message)
    settings.notifications.slack.mode = "bot"
    with pytest.raises(RuntimeError, match="bot token"):
        outbound_module._send_slack(settings, message)
    monkeypatch.setattr(outbound_module, "get_secret", lambda name: "token")
    monkeypatch.setattr(
        outbound_module.httpx,
        "post",
        lambda *args, **kwargs: _Response(200, {"ok": False, "error": "nope"}),
    )
    with pytest.raises(RuntimeError, match="nope"):
        outbound_module._send_slack(settings, message)

    settings.notifications.signal.enabled = False
    with pytest.raises(RuntimeError, match="disabled"):
        outbound_module._send_signal(settings, message)
    settings.notifications.signal.enabled = True
    settings.notifications.signal.api_url = ""
    with pytest.raises(RuntimeError, match="required"):
        outbound_module._send_signal(settings, message)
    settings.notifications.signal.api_url = "http://127.0.0.1:8080"
    monkeypatch.setattr(
        outbound_module.httpx, "post", lambda *args, **kwargs: _Response(500)
    )
    with pytest.raises(RuntimeError, match="HTTP 500"):
        outbound_module._send_signal(settings, message)


def test_notify_request_skips_and_logs_unknown_channel(monkeypatch, tmp_path: Path) -> None:
    request, token = hilt.create_request(
        tmp_path / "out",
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        questions=[HiltQuestion(id="topic", label="Topic")],
        channels=["pager"],
        job_id="job-1",
    )
    assert hilt_channels.notify_request(
        tmp_path / "out", request, "", settings=_settings()
    ) == []
    results = hilt_channels.notify_request(
        tmp_path / "out", request, token, settings=_settings()
    )
    assert results[0]["ok"] is False
    assert "Unknown channel" in results[0]["detail"]


def test_pending_filters_waiting_jobs(monkeypatch, tmp_path: Path) -> None:
    request, _token = hilt.create_request(
        tmp_path / "out",
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        questions=[HiltQuestion(id="topic", label="Topic")],
        channels=["email"],
        job_id="job-1",
    )
    waiting = SimpleNamespace(
        output=tmp_path / "out", job_id="job-1", status="waiting_input"
    )
    running = SimpleNamespace(
        output=tmp_path / "other", job_id="job-2", status="running"
    )
    jobs = SimpleNamespace(list=lambda: [waiting, running])
    items = pollers_module._pending(jobs)
    assert len(items) == 1
    assert items[0][1].interaction_id == request.interaction_id


def test_poller_guard_clauses(monkeypatch, tmp_path: Path) -> None:
    settings = _settings()
    settings.notifications.email.enabled = False
    pollers_module._poll_email(object(), settings)
    settings.notifications.email.enabled = True
    settings.notifications.email.imap_host = ""
    pollers_module._poll_email(object(), settings)

    settings.notifications.slack.enabled = False
    pollers_module._poll_slack(object(), settings)
    settings.notifications.slack.enabled = True
    settings.notifications.slack.mode = "webhook"
    pollers_module._poll_slack(object(), settings)

    settings.notifications.signal.enabled = False
    pollers_module._poll_signal(object(), settings)
    settings.notifications.signal.enabled = True
    settings.notifications.signal.api_url = ""
    pollers_module._poll_signal(object(), settings)


def test_pollers_loop_swallows_failures(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_wait(seconds):
        calls["n"] += 1
        return calls["n"] > 1

    def poll(jobs, settings):
        raise RuntimeError("poll failed")

    monkeypatch.setattr(pollers_module._STOP, "wait", fake_wait)
    monkeypatch.setattr(pollers_module, "load_settings", lambda: AppSettings())
    pollers_module._loop("email", object(), 5, poll)
    assert calls["n"] == 2


def test_start_and_stop_pollers_branches(monkeypatch) -> None:
    settings = AppSettings()
    settings.notifications.enabled = False
    monkeypatch.setattr(pollers_module, "load_settings", lambda: settings)
    pollers_module.start_pollers(object())

    settings.notifications.enabled = True
    settings.notifications.email.enabled = False
    settings.notifications.slack.enabled = False
    settings.notifications.signal.enabled = False
    pollers_module.start_pollers(object())

    class Thread:
        def join(self, timeout=None):
            return None

    monkeypatch.setattr(pollers_module, "_THREADS", {"email": Thread()})
    pollers_module.stop_pollers()


def test_status_test_channel_branches(monkeypatch) -> None:
    from videoflow.application.hilt_channels import status as status_module

    settings = _settings()
    monkeypatch.setattr(
        status_module, "test_local_channel", lambda title: None, raising=False
    )
    monkeypatch.setattr(status_module.hilt, "test_local_channel", lambda title: None)
    assert status_module.test_channel("local", settings)["ok"] is True

    monkeypatch.setattr(status_module, "_send_email", lambda s, m: "email ok")
    monkeypatch.setattr(status_module, "_send_slack", lambda s, m: "slack ok")
    monkeypatch.setattr(status_module, "_send_signal", lambda s, m: "signal ok")
    assert status_module.test_channel("email", settings)["message"] == "email ok"
    assert status_module.test_channel("slack", settings)["message"] == "slack ok"
    assert status_module.test_channel("signal", settings)["message"] == "signal ok"
    assert status_module.test_channel("pager", settings)["ok"] is False

    def broken(settings, message):
        raise RuntimeError("down")

    monkeypatch.setattr(status_module, "_send_email", broken)
    failed = status_module.test_channel("email", settings)
    assert failed["ok"] is False
    assert "down" in failed["message"]


def test_parse_reply_text_branches() -> None:
    from videoflow.application.hilt_channels import inbound as inbound_module

    assert inbound_module.parse_reply_text("no", kind="approval")[0] == "reject"
    assert inbound_module.parse_reply_text("yes", kind="approval")[0] == "approve"
    assert inbound_module.parse_reply_text("please reject this")[0] == "reject"
    assert inbound_module.parse_reply_text("approved")[0] == "approve"
    action, answers, comment = inbound_module.parse_reply_text(
        '{"action": "reject", "comment": "bad", "topic": "x"}'
    )
    assert (action, answers, comment) == ("reject", {"topic": "x"}, "bad")
    action, answers, _ = inbound_module.parse_reply_text("topic: corruption\nnote: ok")
    assert action == "submit"
    assert answers == {"topic": "corruption", "note": "ok"}
    assert inbound_module.parse_reply_text("{not json")[0] == "submit"


def _reply_setup(tmp_path: Path):
    output = tmp_path / "out"
    request, token = hilt.create_request(
        output,
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        questions=[HiltQuestion(id="topic", label="Topic")],
        channels=["email"],
        job_id="job-1",
        notify=False,
    )
    job = SimpleNamespace(
        output=output,
        job_id="job-1",
        status="waiting_input",
        source=tmp_path / "src.mp4",
        options={},
    )
    started: list[str] = []
    answered: list[str] = []

    class Jobs:
        def list(self):
            return [job]

        def start(self, source, output, options, queue=True):
            started.append(str(output))
            return SimpleNamespace(job_id="resumed-1")

        def mark_answered(self, job_id, resumed_id):
            answered.append((job_id, resumed_id))

    return request, token, Jobs(), started, answered


def test_dispatch_reply_branches(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.hilt_channels import inbound as inbound_module

    request, token, jobs, started, answered = _reply_setup(tmp_path)
    unknown = inbound_module.dispatch_reply(
        jobs, hilt_channels.InboundReply(token="missing", action="submit")
    )
    assert unknown["code"] == "hilt_token_not_found"
    assert inbound_module.dispatch_reply(
        jobs,
        hilt_channels.InboundReply(token=token, action="submit", channel="slack"),
    )["code"] == "hilt_channel_not_allowed"

    monkeypatch.setattr(
        hilt, "save_attachment", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad"))
    )
    bad_attachment = inbound_module.dispatch_reply(
        jobs,
        hilt_channels.InboundReply(
            token=token,
            action="submit",
            channel="email",
            attachments=[hilt_channels.InboundAttachment(filename="x", data=b"x")],
        ),
    )
    assert bad_attachment["code"] == "hilt_attachment_invalid"
    monkeypatch.undo()

    monkeypatch.setattr(
        hilt, "respond", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad"))
    )
    bad_response = inbound_module.dispatch_reply(
        jobs,
        hilt_channels.InboundReply(token=token, action="submit", channel="email"),
    )
    assert bad_response["code"] == "hilt_response_invalid"
    monkeypatch.undo()

    success = inbound_module.dispatch_reply(
        jobs,
        hilt_channels.InboundReply(
            token=token, action="submit", channel="email", comment="topic: x"
        ),
    )
    assert success["ok"] is True
    assert started and answered
