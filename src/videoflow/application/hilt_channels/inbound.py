"""Inbound HILT reply parsing and durable interaction dispatch."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

from videoflow.application import hilt
from videoflow.application.hilt_channels.models import (
    _ANSWER_LINE,
    TOKEN,
    InboundReply,
)
from videoflow.domain.hilt import HiltAttachment, HiltRequest


def extract_token(text: str) -> str:
    match = TOKEN.search(text or "")
    return match.group(1) if match else ""


def parse_reply_text(text: str, *, kind: str = "") -> tuple[str, dict[str, Any], str]:
    """Return action, answers, and the original comment from a plain reply."""

    cleaned = (text or "").strip()
    action = "submit"
    if kind == "approval":
        lowered = cleaned.casefold()
        action = (
            "reject"
            if re.search(r"\b(reject|rejected|no)\b", lowered)
            else "approve"
        )
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
                if str(payload.get("action") or "") in {
                    "approve",
                    "reject",
                    "submit",
                }:
                    action = str(payload["action"])
                if payload.get("comment"):
                    cleaned = str(payload["comment"])
        except ValueError:
            pass
    if not answers:
        for line in cleaned.splitlines():
            match = _ANSWER_LINE.match(line)
            if match and match.group(1).casefold() not in {
                "approve",
                "reject",
                "action",
            }:
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
        return {
            "ok": False,
            "code": "hilt_token_not_found",
            "message": "Unknown token.",
        }
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
    answers = {
        key: value for key, value in answers.items() if key in known_questions
    }
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
        return {
            "ok": False,
            "code": "hilt_response_invalid",
            "message": str(exc),
        }
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
