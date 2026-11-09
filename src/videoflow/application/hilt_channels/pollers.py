"""Background pollers for e-mail, Slack, and Signal replies."""

from __future__ import annotations

import contextlib
import email
import imaplib
import logging
import threading
from email.utils import parseaddr
from typing import Any

import httpx

from videoflow.application import hilt
from videoflow.application.hilt_channels.inbound import (
    _match_request,
    dispatch_reply,
    extract_token,
)
from videoflow.application.hilt_channels.models import (
    InboundAttachment,
    InboundReply,
)
from videoflow.application.hilt_channels.webhooks import _slack_attachments
from videoflow.application.secrets import get_secret
from videoflow.application.settings import AppSettings, load_settings
from videoflow.domain.hilt import HiltRequest

logger = logging.getLogger(__name__)

_THREADS: dict[str, threading.Thread] = {}
_STOP = threading.Event()
_LOCK = threading.RLock()


def _pending(jobs: Any) -> list[tuple[Any, HiltRequest]]:
    items: list[tuple[Any, HiltRequest]] = []
    for job in jobs.list():
        if job.status not in {"waiting_approval", "waiting_input"}:
            continue
        for request in hilt.pending_for_job(job.output, str(job.job_id)):
            items.append((job, request))
    return items


def _poll_email(jobs: Any, settings: AppSettings) -> None:
    config = settings.notifications.email
    if not config.enabled or not config.imap_host or not config.imap_user:
        return
    pending = [item for item in _pending(jobs) if "email" in item[1].channels]
    if not pending:
        return
    password = get_secret(config.imap_password_secret)
    if config.imap_ssl:
        client: imaplib.IMAP4 = imaplib.IMAP4_SSL(
            config.imap_host, config.imap_port
        )
    else:
        client = imaplib.IMAP4(config.imap_host, config.imap_port)
    try:
        client.login(config.imap_user, password)
        client.select(config.imap_folder)
        status, data = client.search(None, "UNSEEN")
        if status != "OK":
            return
        for number in (data[0] or b"").split():
            status, message_data = client.fetch(number, "(RFC822)")
            if status != "OK" or not message_data:
                continue
            raw = message_data[0][1]
            parsed = email.message_from_bytes(raw)
            sender = parseaddr(parsed.get("From", ""))[1]
            if config.allowed_senders and not any(
                item.casefold() in sender.casefold()
                for item in config.allowed_senders
            ):
                continue
            text = _email_text(parsed)
            token = extract_token(f"{parsed.get('Subject', '')}\n{text}")
            if not token or _match_request(jobs, token) is None:
                continue
            attachments = _email_attachments(parsed, config.max_attachment_mb)
            dispatch_reply(
                jobs,
                InboundReply(
                    token=token,
                    action="submit",
                    comment=text,
                    attachments=attachments,
                    responder=sender,
                    channel="email",
                ),
            )
            client.store(number, "+FLAGS", "\\Seen")
    finally:
        with contextlib.suppress(Exception):
            client.logout()


def _email_text(message: Any) -> str:
    if message.is_multipart():
        for part in message.walk():
            if (
                part.get_content_type() == "text/plain"
                and not part.get_filename()
            ):
                try:
                    return str(part.get_content())
                except Exception:  # noqa: BLE001 - fall through
                    continue
        return ""
    try:
        return str(message.get_content())
    except Exception:  # noqa: BLE001 - malformed message
        return ""


def _email_attachments(
    message: Any, max_mb: int
) -> list[InboundAttachment]:
    result: list[InboundAttachment] = []
    if not message.is_multipart():
        return result
    for part in message.walk():
        filename = part.get_filename()
        if not filename:
            continue
        try:
            data = part.get_payload(decode=True) or b""
        except Exception:  # noqa: BLE001 - skip a malformed part
            continue
        if len(data) > max_mb * 1024 * 1024:
            continue
        result.append(
            InboundAttachment(
                filename=filename,
                data=data,
                content_type=part.get_content_type(),
            )
        )
    return result


def _poll_slack(jobs: Any, settings: AppSettings) -> None:
    config = settings.notifications.slack
    if not config.enabled or config.mode != "bot" or not config.channel:
        return
    pending = [item for item in _pending(jobs) if "slack" in item[1].channels]
    if not pending:
        return
    token = get_secret(config.bot_token_secret)
    if not token:
        return
    response = httpx.get(
        "https://slack.com/api/conversations.history",
        headers={"Authorization": f"Bearer {token}"},
        params={"channel": config.channel, "limit": 20},
        timeout=20,
    )
    payload = response.json() if response.content else {}
    if not payload.get("ok"):
        return
    for item in reversed(payload.get("messages") or []):
        if not isinstance(item, dict) or item.get("bot_id"):
            continue
        text = str(item.get("text") or "")
        reply_token = extract_token(text)
        if not reply_token or _match_request(jobs, reply_token) is None:
            continue
        user = str(item.get("user") or "")
        if config.allowed_users and user not in config.allowed_users:
            continue
        dispatch_reply(
            jobs,
            InboundReply(
                token=reply_token,
                action="submit",
                comment=text,
                attachments=_slack_attachments(item.get("files"), settings),
                responder=user,
                channel="slack",
            ),
        )


def _poll_signal(jobs: Any, settings: AppSettings) -> None:
    config = settings.notifications.signal
    if not config.enabled or not config.api_url or not config.number:
        return
    pending = [item for item in _pending(jobs) if "signal" in item[1].channels]
    if not pending:
        return
    headers = {}
    password = get_secret(config.password_secret)
    if password:
        headers["Authorization"] = f"Bearer {password}"
    response = httpx.get(
        f"{config.api_url.rstrip('/')}/v1/receive/{config.number}",
        headers=headers,
        timeout=30,
    )
    if response.status_code >= 400:
        return
    envelopes = response.json()
    if not isinstance(envelopes, list):
        return
    for envelope in envelopes:
        if not isinstance(envelope, dict):
            continue
        data = envelope.get("envelope") or {}
        message = data.get("dataMessage") or {}
        text = str(message.get("message") or "")
        token = extract_token(text)
        if not token or _match_request(jobs, token) is None:
            continue
        sender = str(data.get("sourceNumber") or data.get("source") or "")
        if config.allowed_senders and sender not in config.allowed_senders:
            continue
        attachments: list[InboundAttachment] = []
        for item in message.get("attachments") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            download = httpx.get(
                f"{config.api_url.rstrip('/')}/v1/attachments/{item['id']}",
                headers=headers,
                timeout=60,
            )
            if download.status_code < 400:
                attachments.append(
                    InboundAttachment(
                        filename=str(item.get("filename") or "attachment"),
                        data=download.content,
                        content_type=str(item.get("contentType") or ""),
                    )
                )
        dispatch_reply(
            jobs,
            InboundReply(
                token=token,
                action="submit",
                comment=text,
                attachments=attachments,
                responder=sender,
                channel="signal",
            ),
        )


def _loop(name: str, jobs: Any, interval: int, poll: Any) -> None:
    while not _STOP.wait(max(5, interval)):
        try:
            poll(jobs, load_settings())
        except Exception as exc:  # noqa: BLE001 - a poller must not die
            logger.warning("HILT %s poll failed: %s", name, exc)


def start_pollers(jobs: Any) -> None:
    settings = load_settings()
    if not settings.notifications.enabled:
        return
    _STOP.clear()
    with _LOCK:
        for name, enabled, interval, poll in (
            (
                "email",
                settings.notifications.email.enabled,
                settings.notifications.email.poll_seconds,
                _poll_email,
            ),
            (
                "slack",
                settings.notifications.slack.enabled,
                settings.notifications.slack.poll_seconds,
                _poll_slack,
            ),
            (
                "signal",
                settings.notifications.signal.enabled,
                settings.notifications.signal.poll_seconds,
                _poll_signal,
            ),
        ):
            if not enabled:
                continue
            existing = _THREADS.get(name)
            if existing is not None and existing.is_alive():
                continue
            thread = threading.Thread(
                target=_loop,
                args=(name, jobs, interval, poll),
                name=f"videoflow-hilt-{name}",
                daemon=True,
            )
            _THREADS[name] = thread
            thread.start()


def stop_pollers() -> None:
    _STOP.set()
    with _LOCK:
        for thread in _THREADS.values():
            thread.join(timeout=2)
        _THREADS.clear()
