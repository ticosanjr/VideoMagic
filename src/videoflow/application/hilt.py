"""Durable human-in-the-loop interactions.

The request and response live beside the project output, so a browser, an
e-mail reply, or a chat message can all resolve the same pending step. Failure
to notify never fails the job; the interaction itself remains the source of
truth.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from videoflow.application.clock import now_iso
from videoflow.application.settings import load_settings
from videoflow.domain.errors import (
    HiltAttachmentError,
    HiltResponseError,
    RecipeError,
)
from videoflow.domain.hilt import (
    HiltArtifact,
    HiltAttachment,
    HiltEvent,
    HiltFileRequest,
    HiltQuestion,
    HiltRequest,
    HiltResponse,
)

logger = logging.getLogger(__name__)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
_SLUG = re.compile(r"[^A-Za-z0-9_.-]+")
_MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_json_atomic(path: Path, payload: object) -> None:
    """Public atomic JSON writer for step artifacts."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def hilt_root(output: Path) -> Path:
    return Path(output) / "hilt"


def interaction_dir(output: Path, interaction_id: str) -> Path:
    if not _ID.fullmatch(interaction_id) or interaction_id in {".", ".."}:
        raise HiltResponseError(f"Invalid interaction id: {interaction_id}")
    return hilt_root(output) / interaction_id


def _slug(value: str, *, fallback: str = "item") -> str:
    cleaned = _SLUG.sub("-", value.strip()).strip("-")
    return cleaned[:80] or fallback


def make_interaction_id(step_id: str, gate_id: str) -> str:
    return f"hilt-{_slug(step_id, fallback='step')}-{_slug(gate_id, fallback='review')}"[
        :120
    ]


def _request_path(directory: Path) -> Path:
    return directory / "request.json"


def _response_path(directory: Path) -> Path:
    return directory / "response.json"


def _events_path(directory: Path) -> Path:
    return directory / "events.jsonl"


def _notifications_path(directory: Path) -> Path:
    return directory / "notifications.jsonl"


def _event(directory: Path, event: str, detail: dict[str, Any] | None = None) -> None:
    payload = HiltEvent(at=now_iso(), event=event, detail=detail or {})
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with _events_path(directory).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload.model_dump(mode="json"), sort_keys=True) + "\n")
    except OSError as exc:
        logger.warning("could not write HILT event for %s: %s", directory.name, exc)


def _relative_inside(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        candidate = path.expanduser().resolve(strict=False)
        try:
            return candidate.relative_to(root.resolve(strict=False))
        except ValueError as exc:
            raise HiltResponseError(f"Path is outside the job output: {value}") from exc
    if ".." in path.parts:
        raise HiltResponseError(f"Path is outside the job output: {value}")
    return path


def resolve_output_path(output: Path, value: str) -> Path:
    """Resolve a caller-provided output-relative path without touching the filesystem."""

    return Path(output) / _relative_inside(Path(output), value)


def artifact_for_path(
    output: Path,
    raw: str,
    *,
    artifact_id: str = "",
    label: str = "",
    kind: str = "file",
    description: str = "",
) -> HiltArtifact:
    relative = _relative_inside(output, raw)
    path = (output / relative).resolve(strict=False)
    exists = path.is_file()
    size = path.stat().st_size if exists else 0
    identifier = artifact_id or _slug(relative.stem or relative.name, fallback="artifact")
    return HiltArtifact(
        id=identifier,
        label=label or relative.name or identifier,
        path=relative.as_posix(),
        kind=kind,
        description=description,
        exists=exists,
        size_bytes=size,
    )


def build_artifacts(output: Path, specs: Iterable[str]) -> list[HiltArtifact]:
    """Expand relative paths and globs into reviewable artifacts."""

    result: list[HiltArtifact] = []
    seen: set[str] = set()
    used_ids: set[str] = set()
    for spec in specs:
        raw = str(spec or "").strip()
        if not raw:
            continue
        if any(char in raw for char in "*?["):
            matches = sorted(output.glob(raw))
        else:
            candidate = output / _relative_inside(output, raw)
            matches = (
                sorted(path for path in candidate.rglob("*") if path.is_file())
                if candidate.is_dir()
                else [candidate]
            )
        for path in matches:
            if not path.is_file():
                continue
            relative = path.resolve(strict=False).relative_to(
                output.resolve(strict=False)
            )
            key = relative.as_posix()
            if key in seen:
                continue
            seen.add(key)
            artifact = artifact_for_path(output, key)
            base = artifact.id
            index = 2
            while artifact.id in used_ids:
                artifact.id = f"{base}-{index}"
                index += 1
            used_ids.add(artifact.id)
            result.append(artifact)
    return result


def _desktop_notify(title: str, body: str) -> None:
    if os.environ.get("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "1").strip() == "0":
        return
    message = body.strip() or "Open the studio to respond."
    try:
        if sys.platform.startswith("linux"):
            binary = shutil.which("notify-send")
            if binary:
                subprocess.run(
                    [binary, "--app-name=VideoFlow", title, message],
                    check=False,
                    capture_output=True,
                    timeout=2,
                )
        elif sys.platform == "darwin":
            binary = shutil.which("osascript")
            if binary:
                script = (
                    f'display notification {json.dumps(message)} with title '
                    f'{json.dumps(title)}'
                )
                subprocess.run(
                    [binary, "-e", script],
                    check=False,
                    capture_output=True,
                    timeout=2,
                )
    except (OSError, subprocess.SubprocessError):
        return


def _notify_local(directory: Path, request: HiltRequest) -> None:
    payload = {
        "at": now_iso(),
        "channel": "local",
        "ok": True,
        "title": request.title,
        "message": request.description,
    }
    try:
        with _notifications_path(directory).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError as exc:
        logger.warning("could not record HILT notification: %s", exc)
    _event(directory, "notified", {"channel": "local"})
    _desktop_notify(f"VideoFlow: {request.title}", request.description)


def create_request(
    output: Path,
    *,
    step_id: str,
    gate_id: str,
    kind: str,
    title: str,
    description: str = "",
    summary: str = "",
    checklist: list[str] | None = None,
    severity: str = "info",
    next_step: str = "",
    group: str = "",
    questions: list[HiltQuestion] | list[dict[str, Any]] | None = None,
    files: list[HiltFileRequest] | list[dict[str, Any]] | None = None,
    artifacts: list[HiltArtifact] | list[dict[str, Any]] | None = None,
    channels: list[str] | None = None,
    expires_hours: int = 168,
    approve_label: str = "Approve",
    reject_label: str = "Reject",
    job_id: str = "",
    recipe_id: str = "",
    notify: bool = True,
) -> tuple[HiltRequest, str]:
    """Create or return the deterministic interaction for this step."""

    interaction_id = make_interaction_id(step_id, gate_id)
    directory = interaction_dir(output, interaction_id)
    existing = load_request(output, interaction_id)
    if existing is not None:
        return existing, ""

    normalized_questions = [
        item if isinstance(item, HiltQuestion) else HiltQuestion.model_validate(item)
        for item in (questions or [])
    ]
    normalized_files = [
        item if isinstance(item, HiltFileRequest) else HiltFileRequest.model_validate(item)
        for item in (files or [])
    ]
    normalized_artifacts = [
        item if isinstance(item, HiltArtifact) else HiltArtifact.model_validate(item)
        for item in (artifacts or [])
    ]
    for item in normalized_files:
        if item.target.strip():
            _relative_inside(output, item.target)
    selected_channels = (
        [str(item) for item in channels if str(item)]
        if channels
        else list(load_settings().notifications.default_channels or ["local"])
    )

    token = secrets.token_urlsafe(24)
    created = datetime.now(UTC)
    request = HiltRequest(
        interaction_id=interaction_id,
        job_id=job_id,
        recipe_id=recipe_id,
        step_id=step_id,
        gate_id=gate_id,
        kind=kind,  # type: ignore[arg-type]
        title=title,
        description=description,
        summary=summary,
        checklist=[str(item) for item in (checklist or []) if str(item).strip()][:50],
        severity=severity,  # type: ignore[arg-type]
        next_step=next_step,
        group=group,
        approve_label=approve_label,
        reject_label=reject_label,
        questions=normalized_questions,
        files=normalized_files,
        artifacts=normalized_artifacts,
        channels=selected_channels,
        status="pending",
        created_at=created.isoformat(timespec="seconds"),
        expires_at=(created + timedelta(hours=max(1, expires_hours))).isoformat(
            timespec="seconds"
        ),
        reminder_at=(created + timedelta(hours=min(24, max(1, expires_hours)))).isoformat(
            timespec="seconds"
        ),
        token_required=any(item != "local" for item in selected_channels),
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "files").mkdir(parents=True, exist_ok=True)
    _write_json(_request_path(directory), request.model_dump(mode="json"))
    _event(directory, "created", {"kind": kind, "channels": selected_channels})
    if notify:
        _notify_local(directory, request)
    return request, token


def load_request(output: Path, interaction_id: str) -> HiltRequest | None:
    try:
        directory = interaction_dir(output, interaction_id)
    except HiltResponseError:
        return None
    payload = _read_json(_request_path(directory))
    if payload is None:
        return None
    try:
        return HiltRequest.model_validate(payload)
    except ValueError:
        return None


def load_response(output: Path, interaction_id: str) -> HiltResponse | None:
    try:
        directory = interaction_dir(output, interaction_id)
    except HiltResponseError:
        return None
    payload = _read_json(_response_path(directory))
    if payload is None:
        return None
    try:
        return HiltResponse.model_validate(payload)
    except ValueError:
        return None


def list_requests(output: Path, *, job_id: str = "") -> list[HiltRequest]:
    root = hilt_root(output)
    if not root.is_dir():
        return []
    result: list[HiltRequest] = []
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        request = load_request(output, directory.name)
        if request is None:
            continue
        if job_id and request.job_id and request.job_id != job_id:
            continue
        result.append(request)
    result.sort(key=lambda item: item.created_at, reverse=True)
    return result


def find_request(output: Path, job_id: str, interaction_id: str) -> HiltRequest:
    request = load_request(output, interaction_id)
    if request is None or (request.job_id and request.job_id != job_id):
        raise HiltResponseError(f"Unknown interaction: {interaction_id}")
    return request


def _validate_answer(question: HiltQuestion, value: Any) -> Any:
    if question.type == "boolean":
        if not isinstance(value, bool):
            raise HiltResponseError(f"{question.id} must be true or false")
        return value
    if question.type == "number":
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise HiltResponseError(f"{question.id} must be a number") from exc
    if question.type == "choice":
        if value not in question.options:
            raise HiltResponseError(f"{question.id} is not one of the allowed options")
        return value
    if question.type == "file":
        return value
    if not isinstance(value, (str, int, float)):
        raise HiltResponseError(f"{question.id} must be text")
    return value


def _validate_response(
    request: HiltRequest,
    response: HiltResponse,
) -> None:
    if request.status != "pending":
        raise HiltResponseError(
            f"Interaction {request.interaction_id} is already {request.status}"
        )
    if request.kind == "approval":
        if response.action not in {"approve", "reject"}:
            raise HiltResponseError("This interaction requires approve or reject")
    elif response.action not in {"submit", "approve"}:
        raise HiltResponseError("This interaction requires a submitted answer")

    known = {question.id for question in request.questions}
    unknown = sorted(set(response.answers) - known)
    if unknown:
        raise HiltResponseError(f"Unknown answers: {', '.join(unknown)}")
    for question in request.questions:
        value = response.answers.get(question.id)
        if question.type == "file":
            if question.required and not any(
                item.request_id == question.id for item in response.attachments
            ):
                raise HiltResponseError(f"{question.label} needs a file")
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            if question.required:
                raise HiltResponseError(f"{question.label} is required")
            continue
        _validate_answer(question, value)

    for file_request in request.files:
        matches = [
            item for item in response.attachments if item.request_id == file_request.id
        ]
        if file_request.required and not matches:
            raise HiltResponseError(f"{file_request.label} needs a file")


def _verify_attachments(output: Path, request: HiltRequest, response: HiltResponse) -> None:
    directory = interaction_dir(output, request.interaction_id).resolve(strict=False)
    total = 0
    known = {item.id for item in request.files} | {
        item.id for item in request.questions if item.type == "file"
    }
    for attachment in response.attachments:
        if attachment.request_id and attachment.request_id not in known:
            raise HiltResponseError(
                f"Unknown file request: {attachment.request_id}"
            )
        path = (directory / attachment.stored_path).resolve(strict=False)
        if not path.is_relative_to(directory) or not path.is_file():
            raise HiltResponseError(f"Attachment is missing: {attachment.original_name}")
        size = path.stat().st_size
        if size != attachment.size_bytes:
            raise HiltResponseError(
                f"Attachment changed after upload: {attachment.original_name}"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if attachment.sha256 and not hmac.compare_digest(digest, attachment.sha256):
            raise HiltResponseError(
                f"Attachment checksum failed: {attachment.original_name}"
            )
        attachment.sha256 = digest
        total += size
    if total > _MAX_TOTAL_BYTES:
        raise HiltAttachmentError("The uploaded files exceed the total size limit")


def respond(
    output: Path,
    job_id: str,
    interaction_id: str,
    *,
    action: str = "submit",
    answers: dict[str, Any] | None = None,
    comment: str = "",
    attachments: list[HiltAttachment] | list[dict[str, Any]] | None = None,
    responder: str = "local",
    channel: str = "local",
    token: str = "",
) -> tuple[HiltRequest, HiltResponse]:
    request = find_request(output, job_id, interaction_id)
    existing = load_response(output, interaction_id)
    if existing is not None:
        return request, existing
    if request.token_required and channel != "local":
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not token or not hmac.compare_digest(digest, request.token_hash):
            raise HiltResponseError("A valid response token is required")
    if action not in {"approve", "reject", "submit"}:
        raise HiltResponseError(f"Unknown response action: {action}")
    normalized_attachments = [
        item if isinstance(item, HiltAttachment) else HiltAttachment.model_validate(item)
        for item in (attachments or [])
    ]
    known_paths = {item.stored_path for item in normalized_attachments}
    for item in uploaded_attachments(output, interaction_id):
        if item.stored_path not in known_paths:
            normalized_attachments.append(item)
            known_paths.add(item.stored_path)
    response = HiltResponse(
        interaction_id=interaction_id,
        action=action,  # type: ignore[arg-type]
        answers=dict(answers or {}),
        comment=comment.strip(),
        attachments=normalized_attachments,
        responder=responder,
        response_channel=channel,
        received_at=now_iso(),
    )
    _validate_response(request, response)
    _verify_attachments(output, request, response)
    directory = interaction_dir(output, interaction_id)
    response.received_at = now_iso()
    request.status = (
        "approved"
        if request.kind == "approval" and action == "approve"
        else "rejected"
        if request.kind == "approval"
        else "answered"
    )
    _write_json(_response_path(directory), response.model_dump(mode="json"))
    _write_json(_request_path(directory), request.model_dump(mode="json"))
    _event(
        directory,
        "responded",
        {
            "action": action,
            "channel": channel,
            "attachments": len(response.attachments),
        },
    )
    return request, response


def mark_resumed(output: Path, interaction_id: str, resumed_job_id: str) -> None:
    response = load_response(output, interaction_id)
    if response is None:
        return
    response.resumed_job_id = resumed_job_id
    _write_json(
        _response_path(interaction_dir(output, interaction_id)),
        response.model_dump(mode="json"),
    )


def cancel_request(output: Path, interaction_id: str) -> HiltRequest:
    request = load_request(output, interaction_id)
    if request is None:
        raise HiltResponseError(f"Unknown interaction: {interaction_id}")
    if request.status == "pending":
        request.status = "cancelled"
        directory = interaction_dir(output, interaction_id)
        _write_json(_request_path(directory), request.model_dump(mode="json"))
        _event(directory, "cancelled", {})
    return request


def save_attachment(
    output: Path,
    interaction_id: str,
    *,
    request_id: str = "",
    filename: str,
    data: bytes,
    content_type: str = "",
) -> HiltAttachment:
    request = load_request(output, interaction_id)
    if request is None:
        raise HiltResponseError(f"Unknown interaction: {interaction_id}")
    if request.status != "pending":
        raise HiltResponseError(
            f"Interaction {interaction_id} is already {request.status}"
        )
    file_request: HiltFileRequest | None = None
    if request_id:
        file_request = next(
            (item for item in request.files if item.id == request_id), None
        )
        if file_request is None:
            question = next(
                (
                    item
                    for item in request.questions
                    if item.id == request_id and item.type == "file"
                ),
                None,
            )
            if question is None:
                raise HiltResponseError(f"Unknown file request: {request_id}")
            max_mb = question.max_mb
            accept = question.accept
        else:
            max_mb = file_request.max_mb
            accept = file_request.accept
    elif len(request.files) == 1:
        file_request = request.files[0]
        request_id = file_request.id
        max_mb = file_request.max_mb
        accept = file_request.accept
    else:
        raise HiltResponseError("Choose which requested file this attachment answers")

    if len(data) > max_mb * 1024 * 1024:
        raise HiltAttachmentError(
            f"{filename} is larger than the {max_mb} MB limit"
        )
    safe_name = Path(filename or "attachment").name.strip() or "attachment"
    safe_name = _SLUG.sub("-", safe_name)[:200] or "attachment"
    if accept:
        lowered = safe_name.casefold()
        if not any(
            lowered.endswith(str(item).casefold())
            or str(item).casefold() in (content_type or "").casefold()
            for item in accept
        ):
            raise HiltAttachmentError(
                f"{filename} is not one of the accepted types: {', '.join(accept)}"
            )
    directory = interaction_dir(output, interaction_id)
    target_dir = directory / "files" / _slug(request_id or "files")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    if target.exists():
        target = target.with_name(
            f"{target.stem}-{hashlib.sha256(data).hexdigest()[:8]}{target.suffix}"
        )
    target.write_bytes(data)
    relative = target.relative_to(directory).as_posix()
    attachment = HiltAttachment(
        request_id=request_id,
        original_name=Path(filename or safe_name).name,
        stored_path=relative,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        content_type=content_type,
    )
    _event(
        directory,
        "attachment",
        {"request_id": request_id, "name": attachment.original_name},
    )
    _record_upload(directory, attachment)
    return attachment


def _uploads_path(directory: Path) -> Path:
    return directory / "uploads.json"


def _record_upload(directory: Path, attachment: HiltAttachment) -> None:
    payload = _read_json(_uploads_path(directory)) or {"attachments": []}
    items = payload.get("attachments")
    if not isinstance(items, list):
        items = []
    items = [
        item
        for item in items
        if not (
            isinstance(item, dict)
            and item.get("stored_path") == attachment.stored_path
        )
    ]
    items.append(attachment.model_dump(mode="json"))
    _write_json(_uploads_path(directory), {"attachments": items})


def uploaded_attachments(output: Path, interaction_id: str) -> list[HiltAttachment]:
    directory = interaction_dir(output, interaction_id)
    payload = _read_json(_uploads_path(directory)) or {}
    items = payload.get("attachments")
    if not isinstance(items, list):
        return []
    result: list[HiltAttachment] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            result.append(HiltAttachment.model_validate(item))
        except ValueError:
            continue
    return result


def apply_attachments(
    output: Path,
    request: HiltRequest,
    response: HiltResponse,
) -> list[dict[str, Any]]:
    """Copy accepted files to their requested targets and return a manifest."""

    directory = interaction_dir(output, request.interaction_id)
    by_request: dict[str, list[HiltAttachment]] = {}
    for attachment in response.attachments:
        by_request.setdefault(attachment.request_id, []).append(attachment)
    manifest: list[dict[str, Any]] = []
    for file_request in request.files:
        for attachment in by_request.get(file_request.id, []):
            source = directory / attachment.stored_path
            target: Path | None = None
            if file_request.target.strip():
                relative = _relative_inside(output, file_request.target)
                candidate = output / relative
                if candidate.suffix or file_request.allow_replace is False:
                    target = candidate
                else:
                    target = candidate / attachment.original_name
                if target.exists() and not file_request.allow_replace:
                    raise HiltAttachmentError(
                        f"Refusing to replace {target.name}: replace is disabled"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.hilt.tmp")
                shutil.copy2(source, temporary)
                temporary.replace(target)
            manifest.append(
                {
                    "request_id": file_request.id,
                    "name": attachment.original_name,
                    "stored_path": str(source),
                    "target": str(target) if target is not None else "",
                    "size_bytes": attachment.size_bytes,
                    "sha256": attachment.sha256,
                }
            )
    return manifest


def public_payload(
    output: Path,
    request: HiltRequest,
    response: HiltResponse | None = None,
) -> dict[str, Any]:
    payload = request.public()
    for artifact in payload.get("artifacts", []):
        artifact["download_url"] = (
            f"/api/v1/jobs/{request.job_id}/interactions/"
            f"{request.interaction_id}/artifacts/{artifact['id']}"
        )
    payload["response"] = response.public() if response is not None else None
    payload["expired"] = is_expired(request)
    return payload


def is_expired(request: HiltRequest) -> bool:
    if not request.expires_at:
        return False
    try:
        deadline = datetime.fromisoformat(request.expires_at)
    except ValueError:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return datetime.now(UTC) > deadline


def pending_for_job(output: Path, job_id: str) -> list[HiltRequest]:
    return [
        request
        for request in list_requests(output, job_id=job_id)
        if request.status == "pending"
    ]


def channels_status() -> dict[str, object]:
    return {
        "ok": True,
        "default": ["local"],
        "channels": [
            {
                "id": "local",
                "label": "Studio + desktop",
                "enabled": True,
                "available": True,
                "detail": "In-app panel and a best-effort desktop notification.",
            }
        ],
    }


def test_local_channel(title: str = "VideoFlow HILT test") -> dict[str, object]:
    _desktop_notify(title, "Local notifications are working.")
    return {
        "ok": True,
        "channel": "local",
        "available": True,
        "message": "Local notification attempted.",
    }


def require_response(output: Path, interaction_id: str) -> HiltResponse:
    response = load_response(output, interaction_id)
    if response is None:
        raise RecipeError(
            f"Interaction {interaction_id} is still waiting for a human response"
        )
    return response


def unresolved_files(request: HiltRequest, response: HiltResponse) -> list[str]:
    missing: list[str] = []
    for file_request in request.files:
        if file_request.required and not any(
            item.request_id == file_request.id for item in response.attachments
        ):
            missing.append(file_request.label)
    return missing
