"""HILT channel models, token patterns, and notification logging."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from videoflow.application import hilt
from videoflow.domain.hilt import HiltRequest

logger = logging.getLogger(__name__)

TOKEN = re.compile(r"#([A-Za-z0-9_-]{20,})")
_VERB = re.compile(r"\b(approve|approved|reject|rejected|yes|no)\b", re.IGNORECASE)
_ANSWER_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_.-]*)\s*[:=]\s*(.+?)\s*$")


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
