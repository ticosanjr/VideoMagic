"""HILT notification channels: local, e-mail, Slack, and Signal.

The channel layer is deliberately best-effort. A failed notification is logged
beside the interaction and never fails the job that is waiting for a human.
Inbound replies resolve the same durable interaction through ``hilt.respond``.
"""

from videoflow.application.hilt_channels.inbound import (
    _match_request,
    dispatch_reply,
    extract_token,
    parse_reply_text,
)
from videoflow.application.hilt_channels.models import (
    TOKEN,
    InboundAttachment,
    InboundReply,
    OutboundMessage,
    _notification_log,
)
from videoflow.application.hilt_channels.outbound import (
    _send_email,
    _send_signal,
    _send_slack,
    message_for,
    notify_request,
)
from videoflow.application.hilt_channels.pollers import (
    _email_attachments,
    _email_text,
    _loop,
    _pending,
    _poll_email,
    _poll_signal,
    _poll_slack,
    start_pollers,
    stop_pollers,
)
from videoflow.application.hilt_channels.status import (
    channels_status,
    test_channel,
)
from videoflow.application.hilt_channels.webhooks import (
    _slack_attachments,
    ingest_email_payload,
    ingest_slack_event,
    verify_slack_signature,
)

__all__ = [
    "TOKEN",
    "InboundAttachment",
    "InboundReply",
    "OutboundMessage",
    "_email_attachments",
    "_email_text",
    "_loop",
    "_match_request",
    "_notification_log",
    "_pending",
    "_poll_email",
    "_poll_signal",
    "_poll_slack",
    "_send_email",
    "_send_signal",
    "_send_slack",
    "_slack_attachments",
    "channels_status",
    "dispatch_reply",
    "extract_token",
    "ingest_email_payload",
    "ingest_slack_event",
    "message_for",
    "notify_request",
    "parse_reply_text",
    "start_pollers",
    "stop_pollers",
    "test_channel",
    "verify_slack_signature",
]
