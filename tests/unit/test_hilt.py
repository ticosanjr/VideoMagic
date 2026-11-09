from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from videoflow.application import hilt
from videoflow.domain.errors import HiltAttachmentError, HiltResponseError
from videoflow.domain.hilt import HiltFileRequest, HiltQuestion


def _request(output: Path, **kwargs):
    return hilt.create_request(
        output,
        step_id="ask",
        gate_id="brief",
        kind="question",
        title="Brief",
        questions=[
            HiltQuestion(id="topic", label="Topic", type="text", required=True),
            HiltQuestion(
                id="tone",
                label="Tone",
                type="choice",
                required=True,
                options=["calm", "urgent"],
            ),
        ],
        **kwargs,
    )


def test_create_and_respond_to_a_question(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _token = _request(output)
    assert request.status == "pending"
    assert hilt.load_request(output, request.interaction_id) is not None

    _request_obj, response = hilt.respond(
        output,
        "job-1",
        request.interaction_id,
        action="submit",
        answers={"topic": "Corruption", "tone": "calm"},
        comment="Looks good",
        channel="local",
    )

    assert response.answers["topic"] == "Corruption"
    loaded = hilt.load_request(output, request.interaction_id)
    assert loaded is not None and loaded.status == "answered"
    assert hilt.load_response(output, request.interaction_id) is not None
    assert (output / "hilt" / request.interaction_id / "events.jsonl").is_file()


def test_required_answer_and_choice_validation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _token = _request(output)

    with pytest.raises(HiltResponseError, match="Topic is required"):
        hilt.respond(output, "job-1", request.interaction_id, answers={"tone": "calm"})

    with pytest.raises(HiltResponseError, match="allowed options"):
        hilt.respond(
            output,
            "job-1",
            request.interaction_id,
            answers={"topic": "x", "tone": "angry"},
        )


def test_attachment_round_trip_and_target_copy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _token = hilt.create_request(
        output,
        step_id="files",
        gate_id="research",
        kind="files",
        title="Research",
        files=[
            HiltFileRequest(
                id="agent_a",
                label="Agent A",
                required=True,
                accept=[".md"],
                target="research/agent-a.md",
            )
        ],
    )
    payload = b"# Research\n"
    attachment = hilt.save_attachment(
        output,
        request.interaction_id,
        request_id="agent_a",
        filename="agent-a.md",
        data=payload,
        content_type="text/markdown",
    )
    assert attachment.sha256 == hashlib.sha256(payload).hexdigest()

    _request_obj, response = hilt.respond(
        output,
        "job-1",
        request.interaction_id,
        action="submit",
        attachments=[attachment],
    )
    manifest = hilt.apply_attachments(output, request, response)
    target = output / "research" / "agent-a.md"
    assert target.read_text(encoding="utf-8") == "# Research\n"
    assert manifest[0]["sha256"] == attachment.sha256


def test_external_channel_requires_the_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, token = _request(output, channels=["local", "email"])

    with pytest.raises(HiltResponseError, match="token"):
        hilt.respond(
            output,
            "job-1",
            request.interaction_id,
            answers={"topic": "x", "tone": "calm"},
            channel="email",
        )

    _request_obj, response = hilt.respond(
        output,
        "job-1",
        request.interaction_id,
        answers={"topic": "x", "tone": "calm"},
        channel="email",
        token=token,
    )
    assert response.response_channel == "email"


def test_path_traversal_and_missing_file_are_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _token = hilt.create_request(
        output,
        step_id="files",
        gate_id="research",
        kind="files",
        title="Research",
        files=[
            HiltFileRequest(
                id="a", label="A", required=True, accept=[".md"], max_mb=1
            )
        ],
    )

    with pytest.raises(HiltResponseError):
        hilt.create_request(
            output,
            step_id="files",
            gate_id="escape",
            kind="files",
            title="Escape",
            files=[
                HiltFileRequest(
                    id="a", label="A", required=True, target="../escape.md"
                )
            ],
        )
    with pytest.raises(HiltAttachmentError):
        hilt.save_attachment(
            output,
            request.interaction_id,
            request_id="a",
            filename="bad.exe",
            data=b"x",
        )
    with pytest.raises(HiltAttachmentError):
        hilt.save_attachment(
            output,
            request.interaction_id,
            request_id="a",
            filename="a.md",
            data=b"x" * (2 * 1024 * 1024),
        )


def test_public_payload_hides_the_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _token = _request(output)
    payload = hilt.public_payload(output, request)
    assert "token_hash" not in payload
    assert payload["response_url"].endswith("/respond")
    assert json.loads(json.dumps(payload))["interaction_id"] == request.interaction_id
