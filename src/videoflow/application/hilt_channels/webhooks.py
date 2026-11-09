"""Slack and e-mail webhook ingestion."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

import httpx

from videoflow.application.hilt_channels.inbound import (
    dispatch_reply,
    extract_token,
)
from videoflow.application.hilt_channels.models import (
    InboundAttachment,
    InboundReply,
)
from videoflow.application.secrets import get_secret
from videoflow.application.settings import AppSettings, load_settings


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
    expected = (
        "v0="
        + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def _slack_attachments(
    files: Any, settings: AppSettings
) -> list[InboundAttachment]:
    result: list[InboundAttachment] = []
    bot_token = get_secret(settings.notifications.slack.bot_token_secret)
    for file_item in files or []:
        if not isinstance(file_item, dict):
            continue
        url = str(
            file_item.get("url_private_download")
            or file_item.get("url_private")
            or ""
        )
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
        expected = hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return {"ok": False, "code": "invalid_signature"}
    sender = str(payload.get("from") or "")
    allowed = load_settings().notifications.email.allowed_senders
    if allowed and not any(
        item.casefold() in sender.casefold() for item in allowed
    ):
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
