from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace

from videoflow.application import hilt, hilt_channels
from videoflow.application.settings import AppSettings
from videoflow.domain.hilt import HiltQuestion


class FakeJob:
    def __init__(self, output: Path) -> None:
        self.job_id = "job-1"
        self.status = "waiting_input"
        self.output = output
        self.source = output.parent / "source.mp4"
        self.options = {"mode": "recipe"}
        self.message = "waiting"


class FakeJobs:
    def __init__(self, job: FakeJob) -> None:
        self.job = job
        self.resumed = None
        self.answered = None

    def list(self):
        return [self.job]

    def get(self, job_id: str):
        if job_id == self.job.job_id:
            return self.job
        if self.resumed and job_id == self.resumed.job_id:
            return self.resumed
        raise KeyError(job_id)

    def start(self, source, output, options, *, queue=False):
        self.resumed = SimpleNamespace(
            job_id="job-2",
            source=source,
            output=output,
            options=options,
            status="queued",
        )
        return self.resumed

    def mark_answered(self, job_id: str, resumed_id: str) -> None:
        self.answered = (job_id, resumed_id)
        self.job.status = "answered"


def _waiting_request(tmp_path: Path, monkeypatch) -> tuple[FakeJobs, hilt.HiltRequest, str]:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, token = hilt.create_request(
        output,
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        questions=[HiltQuestion(id="topic", label="Topic", type="text")],
        channels=["local", "email"],
        job_id="job-1",
    )
    job = FakeJob(output)
    return FakeJobs(job), request, token


def test_extract_token_and_reply_parsing() -> None:
    assert hilt_channels.extract_token("token #abcDEF0123456789xyzABC") == "abcDEF0123456789xyzABC"
    action, answers, comment = hilt_channels.parse_reply_text(
        "topic: corruption\ncomment: looks good"
    )
    assert action == "submit"
    assert answers == {"topic": "corruption", "comment": "looks good"}
    assert "corruption" in comment

    action, answers, _ = hilt_channels.parse_reply_text(
        '{"topic": "x", "action": "submit"}'
    )
    assert action == "submit"
    assert answers == {"topic": "x"}


def test_dispatch_email_reply_resumes_the_job(tmp_path: Path, monkeypatch) -> None:
    jobs, request, token = _waiting_request(tmp_path, monkeypatch)
    result = hilt_channels.dispatch_reply(
        jobs,
        hilt_channels.InboundReply(
            token=token,
            action="submit",
            comment="topic: Corruption",
            responder="editor@example.com",
            channel="email",
        ),
    )
    assert result["ok"] is True, result
    assert result["job_id"] == "job-2"
    assert jobs.answered == ("job-1", "job-2")
    response = hilt.load_response(jobs.job.output, request.interaction_id)
    assert response is not None
    assert response.answers["topic"] == "Corruption"


def test_dispatch_with_an_unknown_token_is_rejected(tmp_path: Path, monkeypatch) -> None:
    jobs, _request, _token = _waiting_request(tmp_path, monkeypatch)
    result = hilt_channels.dispatch_reply(
        jobs,
        hilt_channels.InboundReply(
            token="not-a-token", action="submit", comment="topic: x", channel="email"
        ),
    )
    assert result["ok"] is False
    assert result["code"] == "hilt_token_not_found"


def test_slack_signature_verification(monkeypatch) -> None:
    body = b'{"type":"event_callback"}'
    timestamp = "1700000000"
    secret = "s3cret"
    signature = "v0=" + hmac.new(
        secret.encode(), b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
    ).hexdigest()
    monkeypatch.setattr(hilt_channels.time, "time", lambda: 1700000000)
    assert hilt_channels.verify_slack_signature(body, timestamp, signature, secret)
    assert not hilt_channels.verify_slack_signature(body, "1700000000", "v0=bad", secret)


def test_email_message_text_and_attachment() -> None:
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = "editor@example.com"
    message["Subject"] = "Re: #token"
    message.set_content("topic: Corruption")
    message.add_attachment(
        b"# research\n", maintype="text", subtype="markdown", filename="agent.md"
    )
    assert "Corruption" in hilt_channels._email_text(message)
    attachments = hilt_channels._email_attachments(message, 10)
    assert attachments[0].filename == "agent.md"
    assert attachments[0].data == b"# research\n"


def test_channel_status_and_test_local(monkeypatch) -> None:
    settings = AppSettings()
    status = hilt_channels.channels_status(settings)
    assert status["channels"][0]["id"] == "local"
    result = hilt_channels.test_channel("local", settings)
    assert result["ok"] is True


def test_notification_log_is_written(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _token = hilt.create_request(
        output,
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        questions=[HiltQuestion(id="topic", label="Topic")],
        job_id="job-1",
    )
    hilt_channels._notification_log(output, request, "email", ok=True, detail="sent")
    path = output / "hilt" / request.interaction_id / "notifications.jsonl"
    payload = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert payload["channel"] == "email" and payload["ok"] is True


def test_signal_send_uses_the_rest_contract(monkeypatch) -> None:
    calls = {}

    class FakeResponse:
        status_code = 200

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["json"] = kwargs.get("json")
        return FakeResponse()

    monkeypatch.setattr(hilt_channels.httpx, "post", fake_post)
    settings = AppSettings()
    settings.notifications.signal.enabled = True
    settings.notifications.signal.number = "+15550001"
    settings.notifications.signal.recipients = ["+15550002"]
    message = hilt_channels.OutboundMessage(
        title="Review",
        body="Please approve",
        interaction_id="hilt-1",
        job_id="job-1",
        token="token",
        url="http://localhost",
        expires_at="",
    )
    detail = hilt_channels._send_signal(settings, message)
    assert "sent" in detail
    assert calls["url"].endswith("/v2/send")
    assert calls["json"]["recipients"] == ["+15550002"]
