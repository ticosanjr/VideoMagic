"""HILT notification channels: local, e-mail, Slack, and Signal.

The channel layer is deliberately best-effort. A failed notification is logged
beside the interaction and never fails the job that is waiting for a human.
Inbound replies resolve the same durable interaction through ``hilt.respond``.
"""

from __future__ import annotations

import base64
import contextlib
import email
import hashlib
import hmac
import imaplib
import json
import logging
import re
import smtplib
import threading
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

import httpx

from videoflow.application import hilt
from videoflow.application.secrets import get_secret
from videoflow.application.settings import AppSettings, load_settings
from videoflow.domain.hilt import HiltAttachment, HiltRequest

logger = logging.getLogger(__name__)

TOKEN = re.compile(r"#([A-Za-z0-9_-]{20,})")
_VERB = re.compile(r"\b(approve|approved|reject|rejected|yes|no)\b", re.IGNORECASE)
_ANSWER_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.-]*)\s*[:=]\s*(.+?)\s*$")
_THREADS: dict[str, threading.Thread] = {}
_STOP = threading.Event()
_LOCK = threading.RLock()


@dataclass(frozen=True)
class OutboundMessage:
    title: str
    body: str
    interaction_id: str
    job_id: str
    token: str
    url: str
    expires_at: str
    approve_label: str = "Approve"
    reject_label: str = "Reject"


@dataclass
class InboundAttachment:
    filename: str
    data: bytes
    content_type: str = ""
    request_id: str = ""


@dataclass
class InboundReply:
    token: str
    action: str
    answers: dict[str, Any] = field(default_factory=dict)
    comment: str = ""
    attachments: list[InboundAttachment] = field(default_factory=list)
    responder: str = ""
    channel: str = ""


def _notification_log(
    output: Path,
    request: HiltRequest,
    channel: str,
    *,
    ok: bool,
    detail: str = "",
) -> None:
    path = hilt.interaction_dir(output, request.interaction_id) / "notifications.jsonl"
    payload = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "channel": channel,
        "ok": ok,
        "detail": detail,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError as exc:
        logger.warning("could not record %s notification: %s", channel, exc)


def message_for(request: HiltRequest, token: str, *, base_url: str = "") -> OutboundMessage:
    url = f"{base_url.rstrip('/')}/?job={request.job_id}&interaction={request.interaction_id}"
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
            f"Slack chat.postMessage failed: {payload.get('error') or response.status_code}"
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


def channels_status(settings: AppSettings | None = None) -> dict[str, object]:
    current = settings or load_settings()
    config = current.notifications
    items = [
        {
            "id": "local",
            "label": "Studio + desktop",
            "enabled": config.local.enabled,
            "available": config.local.enabled,
            "detail": "In-app panel and a best-effort desktop notification.",
        },
        {
            "id": "email",
            "label": "E-mail",
            "enabled": config.email.enabled,
            "available": bool(
                config.email.enabled
                and config.email.smtp_host
                and config.email.from_address
                and config.email.to_addresses
            ),
            "detail": "SMTP send + IMAP reply polling.",
        },
        {
            "id": "slack",
            "label": "Slack",
            "enabled": config.slack.enabled,
            "available": bool(
                config.slack.enabled
                and (
                    (config.slack.mode == "webhook" and get_secret(config.slack.webhook_secret))
                    or (config.slack.mode == "bot" and get_secret(config.slack.bot_token_secret))
                )
            ),
            "detail": "Webhook or bot send; polling and optional Events API.",
        },
        {
            "id": "signal",
            "label": "Signal",
            "enabled": config.signal.enabled,
            "available": bool(
                config.signal.enabled
                and config.signal.api_url
                and config.signal.number
                and config.signal.recipients
            ),
            "detail": "signal-cli REST send and receive polling.",
        },
    ]
    return {"ok": True, "default": config.default_channels, "channels": items}


def test_channel(name: str, settings: AppSettings | None = None) -> dict[str, object]:
    current = settings or load_settings()
    message = OutboundMessage(
        title="VideoFlow HILT test",
        body="This is a test notification from VideoFlow.",
        interaction_id="test",
        job_id="test",
        token="test-token",
        url=current.notifications.base_url,
        expires_at="",
    )
    try:
        if name == "local":
            hilt.test_local_channel(message.title)
            return {"ok": True, "channel": "local", "message": "Local notification attempted."}
        if name == "email":
            detail = _send_email(current, message)
        elif name == "slack":
            detail = _send_slack(current, message)
        elif name == "signal":
            detail = _send_signal(current, message)
        else:
            raise ValueError(f"Unknown channel: {name}")
        return {"ok": True, "channel": name, "message": detail}
    except Exception as exc:  # noqa: BLE001 - reported to the operator
        return {"ok": False, "channel": name, "message": str(exc)[:500]}


def extract_token(text: str) -> str:
    match = TOKEN.search(text or "")
    return match.group(1) if match else ""


def parse_reply_text(text: str, *, kind: str = "") -> tuple[str, dict[str, Any], str]:
    """Return action, answers, and the original comment from a plain reply."""

    cleaned = (text or "").strip()
    action = "submit"
    if kind == "approval":
        lowered = cleaned.casefold()
        action = "reject" if re.search(r"\b(reject|rejected|no)\b", lowered) else "approve"
    elif re.search(r"\b(reject|rejected)\b", cleaned, re.IGNORECASE):
        action = "reject"
    elif re.search(r"\b(approve|approved)\b", cleaned, re.IGNORECASE):
        action = "approve"
    answers: dict[str, Any] = {}
    if cleaned.startswith("{"):
        try:
            payload = json.loads(cleaned)
            if isinstance(payload, dict):
                answers = {
                    str(key): value
                    for key, value in payload.items()
                    if key not in {"action", "comment"}
                }
                if str(payload.get("action") or "") in {"approve", "reject", "submit"}:
                    action = str(payload["action"])
                if payload.get("comment"):
                    cleaned = str(payload["comment"])
        except ValueError:
            pass
    if not answers:
        for line in cleaned.splitlines():
            match = _ANSWER_LINE.match(line)
            if match and match.group(1).casefold() not in {"approve", "reject", "action"}:
                answers[match.group(1)] = match.group(2)
    return action, answers, cleaned


def _match_request(
    jobs: Any, token: str
) -> tuple[Any, HiltRequest] | None:
    if not token:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    for job in jobs.list():
        if job.status not in {"waiting_approval", "waiting_input"}:
            continue
        for request in hilt.pending_for_job(job.output, str(job.job_id)):
            if request.token_hash and hmac.compare_digest(digest, request.token_hash):
                return job, request
    return None


def dispatch_reply(jobs: Any, reply: InboundReply) -> dict[str, object]:
    match = _match_request(jobs, reply.token)
    if match is None:
        return {"ok": False, "code": "hilt_token_not_found", "message": "Unknown token."}
    job, request = match
    if reply.channel and reply.channel not in request.channels:
        return {
            "ok": False,
            "code": "hilt_channel_not_allowed",
            "message": f"Channel {reply.channel} is not enabled for this interaction.",
        }
    action, answers, comment = parse_reply_text(reply.comment, kind=request.kind)
    if reply.action and reply.action != "submit":
        action = reply.action
    known_questions = {question.id for question in request.questions}
    answers = {key: value for key, value in answers.items() if key in known_questions}
    if not answers and request.kind != "approval" and len(request.questions) == 1:
        answers = {request.questions[0].id: reply.comment}
    existing = hilt.load_response(job.output, request.interaction_id)
    if existing is not None and existing.resumed_job_id:
        return {
            "ok": True,
            "job_id": existing.resumed_job_id,
            "interaction_id": request.interaction_id,
            "channel": reply.channel,
            "duplicate": True,
        }
    attachments: list[HiltAttachment] = []
    for item in reply.attachments:
        target_id = item.request_id
        if not target_id and len(request.files) == 1:
            target_id = request.files[0].id
        try:
            attachments.append(
                hilt.save_attachment(
                    job.output,
                    request.interaction_id,
                    request_id=target_id,
                    filename=item.filename,
                    data=item.data,
                    content_type=item.content_type,
                )
            )
        except Exception as exc:  # noqa: BLE001 - report the bad attachment
            return {
                "ok": False,
                "code": "hilt_attachment_invalid",
                "message": f"Could not accept {item.filename}: {exc}",
            }
    try:
        hilt.respond(
            job.output,
            str(job.job_id),
            request.interaction_id,
            action=action,
            answers=answers,
            comment=comment,
            attachments=attachments,
            responder=reply.responder or reply.channel,
            channel=reply.channel or "local",
            token=reply.token,
        )
    except Exception as exc:  # noqa: BLE001 - return a typed API response
        return {"ok": False, "code": "hilt_response_invalid", "message": str(exc)}
    resumed = jobs.start(
        job.source,
        job.output,
        {**job.options, "resume": True},
        queue=True,
    )
    hilt.mark_resumed(job.output, request.interaction_id, str(resumed.job_id))
    jobs.mark_answered(str(job.job_id), str(resumed.job_id))
    return {
        "ok": True,
        "job_id": str(resumed.job_id),
        "interaction_id": request.interaction_id,
        "channel": reply.channel,
    }


def verify_slack_signature(
    body: bytes, timestamp: str, signature: str, secret: str
) -> bool:
    if not secret or not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False
    except ValueError:
        return False
    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    expected = "v0=" + hmac.new(
        secret.encode("utf-8"), base, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _slack_attachments(
    files: Any, settings: AppSettings
) -> list[InboundAttachment]:
    result: list[InboundAttachment] = []
    bot_token = get_secret(settings.notifications.slack.bot_token_secret)
    for file_item in files or []:
        if not isinstance(file_item, dict):
            continue
        url = str(file_item.get("url_private_download") or file_item.get("url_private") or "")
        if not url:
            continue
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {bot_token}"} if bot_token else {},
            timeout=30,
        )
        if response.status_code < 400:
            result.append(
                InboundAttachment(
                    filename=str(file_item.get("name") or "attachment"),
                    data=response.content,
                    content_type=str(file_item.get("mimetype") or ""),
                )
            )
    return result


def ingest_slack_event(
    payload: dict[str, Any], body: bytes, headers: dict[str, str], jobs: Any
) -> dict[str, object]:
    settings = load_settings()
    secret = get_secret(settings.notifications.slack.signing_secret)
    if secret and not verify_slack_signature(
        body,
        headers.get("x-slack-request-timestamp", ""),
        headers.get("x-slack-signature", ""),
        secret,
    ):
        return {"ok": False, "code": "invalid_signature"}
    if payload.get("type") == "url_verification":
        return {"ok": True, "challenge": payload.get("challenge", "")}
    event = payload.get("event") or {}
    if not isinstance(event, dict) or event.get("type") != "message":
        return {"ok": True, "ignored": True}
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"ok": True, "ignored": True}
    text = str(event.get("text") or "")
    token = extract_token(text)
    if not token:
        return {"ok": True, "ignored": True}
    allowed = settings.notifications.slack.allowed_users
    user = str(event.get("user") or "")
    if allowed and user not in allowed:
        return {"ok": False, "code": "sender_not_allowed"}
    attachments = _slack_attachments(event.get("files"), settings)
    reply = InboundReply(
        token=token,
        action="submit",
        comment=text,
        attachments=attachments,
        responder=user,
        channel="slack",
    )
    return dispatch_reply(jobs, reply)


def ingest_email_payload(
    payload: dict[str, Any], body: bytes, headers: dict[str, str], jobs: Any
) -> dict[str, object]:
    secret = get_secret("VIDEOWFLOW_EMAIL_INBOUND_SECRET")
    if secret:
        signature = headers.get("x-videoflow-signature", "")
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return {"ok": False, "code": "invalid_signature"}
    sender = str(payload.get("from") or "")
    allowed = load_settings().notifications.email.allowed_senders
    if allowed and not any(item.casefold() in sender.casefold() for item in allowed):
        return {"ok": False, "code": "sender_not_allowed"}
    text = f"{payload.get('subject', '')}\n{payload.get('text', '')}"
    token = extract_token(text)
    if not token:
        return {"ok": True, "ignored": True}
    attachments = []
    for item in payload.get("attachments") or []:
        if not isinstance(item, dict) or not item.get("content_base64"):
            continue
        try:
            data = base64.b64decode(str(item["content_base64"]), validate=True)
        except ValueError:
            continue
        if len(data) > 512 * 1024 * 1024:
            continue
        attachments.append(
            InboundAttachment(
                filename=str(item.get("filename") or "attachment"),
                data=data,
                content_type=str(item.get("content_type") or ""),
                request_id=str(item.get("request_id") or ""),
            )
        )
    return dispatch_reply(
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
        client: imaplib.IMAP4 = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
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
                item.casefold() in sender.casefold() for item in config.allowed_senders
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
            if part.get_content_type() == "text/plain" and not part.get_filename():
                try:
                    return str(part.get_content())
                except Exception:  # noqa: BLE001 - fall through
                    continue
        return ""
    try:
        return str(message.get_content())
    except Exception:  # noqa: BLE001 - malformed message
        return ""


def _email_attachments(message: Any, max_mb: int) -> list[InboundAttachment]:
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
