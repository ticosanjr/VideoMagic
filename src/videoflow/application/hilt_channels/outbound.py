"""Outbound HILT notifications over e-mail, Slack, and Signal."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

import httpx

from videoflow.application import hilt
from videoflow.application.hilt_channels.models import (
    OutboundMessage,
    _notification_log,
)
from videoflow.application.secrets import get_secret
from videoflow.application.settings import AppSettings, load_settings
from videoflow.domain.hilt import HiltRequest

logger = logging.getLogger(__name__)


def message_for(
    request: HiltRequest, token: str, *, base_url: str = ""
) -> OutboundMessage:
    url = (
        f"{base_url.rstrip('/')}/?job={request.job_id}"
        f"&interaction={request.interaction_id}"
    )
    lines = [
        f"{request.title}",
        "",
        request.description or "Open VideoFlow to respond.",
        "",
        f"Job: {request.job_id}",
        f"Interaction: {request.interaction_id}",
        f"Reply token: #{token}",
        f"Open: {url}",
    ]
    if request.questions:
        lines.extend(["", "Questions:"])
        for question in request.questions:
            lines.append(f"- {question.id}: {question.label}")
    if request.files:
        lines.extend(["", "Files:"])
        for item in request.files:
            lines.append(f"- {item.id}: {item.label}")
    lines.extend(
        [
            "",
            "Reply with the token in the subject or body. For a question, use "
            "'id: answer' lines or a JSON object. Attach requested files.",
            f"Approve/Reject: {request.approve_label} / {request.reject_label}",
        ]
    )
    return OutboundMessage(
        title=request.title,
        body="\n".join(lines),
        interaction_id=request.interaction_id,
        job_id=request.job_id,
        token=token,
        url=url,
        expires_at=request.expires_at,
        approve_label=request.approve_label,
        reject_label=request.reject_label,
    )


def notify_request(
    output: Path,
    request: HiltRequest,
    token: str,
    *,
    settings: AppSettings | None = None,
) -> list[dict[str, object]]:
    """Send the request to every configured external channel."""

    if not token:
        return []
    current = settings or load_settings()
    if not hilt._notifications_enabled(current):
        return []
    if not current.notifications.notify_hitl:
        return []
    message = message_for(request, token, base_url=current.notifications.base_url)
    results: list[dict[str, object]] = []
    for name in request.channels:
        if name in {"", "local"}:
            continue
        try:
            if name == "email":
                detail = _send_email(current, message)
            elif name == "slack":
                detail = _send_slack(current, message)
            elif name == "signal":
                detail = _send_signal(current, message)
            else:
                raise ValueError(f"Unknown channel: {name}")
            _notification_log(output, request, name, ok=True, detail=detail)
            results.append({"channel": name, "ok": True, "detail": detail})
        except Exception as exc:  # noqa: BLE001 - notification is best effort
            detail = str(exc)[:500]
            _notification_log(output, request, name, ok=False, detail=detail)
            results.append({"channel": name, "ok": False, "detail": detail})
            logger.warning("HILT %s notification failed: %s", name, exc)
    return results


def _send_email(settings: AppSettings, message: OutboundMessage) -> str:
    config = settings.notifications.email
    if not config.enabled:
        raise RuntimeError("E-mail notifications are disabled.")
    if not config.smtp_host or not config.from_address or not config.to_addresses:
        raise RuntimeError("E-mail SMTP host, from address, and recipients are required.")
    password = get_secret(config.smtp_password_secret)
    body = EmailMessage()
    body["Subject"] = f"[VideoFlow] {message.title} #{message.token}"
    body["From"] = config.from_address
    body["To"] = ", ".join(config.to_addresses)
    body.set_content(message.body)
    if config.smtp_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            config.smtp_host, config.smtp_port, timeout=20
        )
    else:
        client = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20)
    with client:
        if config.smtp_starttls and not config.smtp_ssl:
            client.starttls()
        if config.smtp_user:
            client.login(config.smtp_user, password)
        client.send_message(body)
    return f"sent to {len(config.to_addresses)} recipient(s)"


def _send_slack(settings: AppSettings, message: OutboundMessage) -> str:
    config = settings.notifications.slack
    if not config.enabled:
        raise RuntimeError("Slack notifications are disabled.")
    text = f"*{message.title}*\n{message.body}"
    if config.mode == "webhook":
        url = get_secret(config.webhook_secret)
        if not url:
            raise RuntimeError(f"Missing Slack webhook secret {config.webhook_secret}.")
        response = httpx.post(url, json={"text": text}, timeout=20)
        if response.status_code >= 400:
            raise RuntimeError(f"Slack webhook returned HTTP {response.status_code}.")
        return "webhook sent"
    token = get_secret(config.bot_token_secret)
    if not token or not config.channel:
        raise RuntimeError("Slack bot token and channel are required.")
    response = httpx.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": config.channel, "text": text},
        timeout=20,
    )
    payload = response.json() if response.content else {}
    if response.status_code >= 400 or not payload.get("ok"):
        raise RuntimeError(
            "Slack chat.postMessage failed: "
            f"{payload.get('error') or response.status_code}"
        )
    return "chat.postMessage sent"


def _send_signal(settings: AppSettings, message: OutboundMessage) -> str:
    config = settings.notifications.signal
    if not config.enabled:
        raise RuntimeError("Signal notifications are disabled.")
    if not config.api_url or not config.number or not config.recipients:
        raise RuntimeError("Signal API URL, number, and recipients are required.")
    headers = {}
    password = get_secret(config.password_secret)
    if password:
        headers["Authorization"] = f"Bearer {password}"
    response = httpx.post(
        f"{config.api_url.rstrip('/')}/v2/send",
        headers=headers,
        json={
            "message": f"{message.title}\n{message.body}",
            "number": config.number,
            "recipients": config.recipients,
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Signal send returned HTTP {response.status_code}.")
    return f"sent to {len(config.recipients)} recipient(s)"


def test_local_channel(title: str) -> None:
    hilt.test_local_channel(title)
