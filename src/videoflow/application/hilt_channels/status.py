"""Channel availability and test helpers."""

from __future__ import annotations

from videoflow.application import hilt
from videoflow.application.hilt_channels.models import OutboundMessage
from videoflow.application.hilt_channels.outbound import (
    _send_email,
    _send_signal,
    _send_slack,
)
from videoflow.application.secrets import get_secret
from videoflow.application.settings import AppSettings, load_settings


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
                    (
                        config.slack.mode == "webhook"
                        and get_secret(config.slack.webhook_secret)
                    )
                    or (
                        config.slack.mode == "bot"
                        and get_secret(config.slack.bot_token_secret)
                    )
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
            return {
                "ok": True,
                "channel": "local",
                "message": "Local notification attempted.",
            }
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
