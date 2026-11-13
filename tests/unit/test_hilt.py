from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from videoflow.application import hilt
from videoflow.domain.errors import (
    HiltAttachmentError,
    HiltResponseError,
    RecipeError,
)
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


def test_request_metadata_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _token = _request(
        output,
        summary="Check the facts before narration.",
        checklist=["Sources attached", "No unsupported claims"],
        severity="warning",
        next_step="Narration synthesis",
        group="script",
    )
    payload = hilt.public_payload(output, request)

    assert payload["summary"] == "Check the facts before narration."
    assert payload["checklist"] == ["Sources attached", "No unsupported claims"]
    assert payload["severity"] == "warning"
    assert payload["next_step"] == "Narration synthesis"
    assert payload["group"] == "script"


def test_artifact_building_and_deduplication(tmp_path: Path) -> None:
    output = tmp_path / "out"
    (output / "a").mkdir(parents=True)
    (output / "a" / "one.txt").write_text("one", encoding="utf-8")
    (output / "b.txt").write_text("two", encoding="utf-8")
    artifacts = hilt.build_artifacts(output, ["b.txt", "a", "*.txt", ""])
    assert [item.path for item in artifacts] == ["b.txt", "a/one.txt"]
    assert all(item.exists for item in artifacts)

    missing = hilt.artifact_for_path(output, "missing.txt", artifact_id="x")
    assert missing.id == "x"
    assert missing.exists is False


def test_request_lookup_and_expiry(tmp_path: Path) -> None:
    output = tmp_path / "out"
    request, _ = _request(output)
    assert (
        hilt.find_request(output, "", request.interaction_id).interaction_id
        == request.interaction_id
    )
    assert hilt.pending_for_job(output, "") == [request]
    jobbed, _ = _request(tmp_path / "out-job", job_id="job-1")
    with pytest.raises(HiltResponseError):
        hilt.find_request(tmp_path / "out-job", "other-job", jobbed.interaction_id)
    with pytest.raises(HiltResponseError):
        hilt.find_request(output, "", "missing")

    assert hilt.is_expired(request) is False
    expired = request.model_copy(update={"expires_at": "2000-01-01T00:00:00+00:00"})
    assert hilt.is_expired(expired) is True
    invalid = request.model_copy(update={"expires_at": "not-a-date"})
    assert hilt.is_expired(invalid) is False


def test_answer_validation_branches(tmp_path: Path) -> None:
    output = tmp_path / "out"
    request, _ = hilt.create_request(
        output,
        step_id="ask",
        gate_id="ask",
        kind="question",
        title="Ask",
        questions=[
            HiltQuestion(id="flag", label="Flag", type="boolean"),
            HiltQuestion(id="count", label="Count", type="number"),
            HiltQuestion(id="tone", label="Tone", type="choice", options=["a", "b"]),
            HiltQuestion(id="free", label="Free", type="text"),
            HiltQuestion(id="file", label="File", type="file", required=False),
        ],
    )
    question = {item.id: item for item in request.questions}
    assert hilt._validate_answer(question["flag"], True) is True
    assert hilt._validate_answer(question["count"], "2") == 2.0
    assert hilt._validate_answer(question["tone"], "a") == "a"
    assert hilt._validate_answer(question["free"], "hello") == "hello"
    with pytest.raises(HiltResponseError):
        hilt._validate_answer(question["flag"], "yes")
    with pytest.raises(HiltResponseError):
        hilt._validate_answer(question["count"], "x")
    with pytest.raises(HiltResponseError):
        hilt._validate_answer(question["tone"], "z")
    with pytest.raises(HiltResponseError):
        hilt._validate_answer(question["free"], [])


def test_response_validation_rejects_bad_answers(tmp_path: Path) -> None:
    from videoflow.domain.hilt import HiltResponse

    output = tmp_path / "out"
    request, _ = _request(output)
    approval, _ = hilt.create_request(
        output,
        step_id="approval",
        gate_id="approval",
        kind="approval",
        title="Approve",
    )
    with pytest.raises(HiltResponseError, match="approve or reject"):
        hilt._validate_response(
            approval,
            HiltResponse(
                interaction_id=approval.interaction_id,
                action="submit",
            ),
        )
    with pytest.raises(HiltResponseError, match="Unknown answers"):
        hilt._validate_response(
            request,
            HiltResponse(
                interaction_id=request.interaction_id,
                action="approve",
                answers={"other": "x"},
            ),
        )
    with pytest.raises(HiltResponseError, match="required"):
        hilt._validate_response(
            request,
            HiltResponse(interaction_id=request.interaction_id, action="approve"),
        )


def test_cancel_and_mark_resumed(tmp_path: Path) -> None:
    output = tmp_path / "out"
    request, _ = _request(output)
    hilt.mark_resumed(output, request.interaction_id, "job-2")
    assert hilt.load_response(output, request.interaction_id) is None
    cancelled = hilt.cancel_request(output, request.interaction_id)
    assert cancelled.status == "cancelled"
    with pytest.raises(HiltResponseError):
        hilt.cancel_request(output, "missing")


def test_channels_and_require_response(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "out"
    status = hilt.channels_status()
    assert status["ok"] is True
    assert hilt.test_local_channel()["ok"] is True
    request, _ = _request(output)
    with pytest.raises(RecipeError):
        hilt.require_response(output, request.interaction_id)
    response = hilt.respond(
        output,
        "",
        request.interaction_id,
        action="submit",
        answers={"topic": "x", "tone": "calm"},
    )
    assert hilt.require_response(output, request.interaction_id) == response[1]


def test_respond_is_idempotent_and_requires_tokens(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, token = hilt.create_request(
        output,
        step_id="files",
        gate_id="files",
        kind="files",
        title="Files",
        channels=["local", "email"],
        files=[HiltFileRequest(id="file", label="File", required=False)],
    )
    with pytest.raises(HiltResponseError):
        hilt.respond(
            output,
            "",
            request.interaction_id,
            action="submit",
            token="bad",
            channel="email",
        )
    first = hilt.respond(
        output,
        "",
        request.interaction_id,
        action="submit",
        token=token,
        channel="email",
    )
    second = hilt.respond(
        output, "", request.interaction_id, action="submit", token=token, channel="email"
    )
    assert first[1] == second[1]


def test_attachment_verification_rejects_bad_files(tmp_path: Path, monkeypatch) -> None:
    from videoflow.domain.hilt import HiltAttachment, HiltResponse

    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _ = hilt.create_request(
        output,
        step_id="files",
        gate_id="files",
        kind="files",
        title="Files",
        files=[HiltFileRequest(id="file", label="File", required=False)],
    )
    response = HiltResponse(
        interaction_id=request.interaction_id,
        attachments=[
            HiltAttachment(
                request_id="unknown",
                original_name="x.txt",
                stored_path="x.txt",
            )
        ],
    )
    with pytest.raises(HiltResponseError, match="Unknown file"):
        hilt._verify_attachments(output, request, response)

    response = HiltResponse(
        interaction_id=request.interaction_id,
        attachments=[
            HiltAttachment(
                request_id="file",
                original_name="x.txt",
                stored_path="missing.txt",
            )
        ],
    )
    with pytest.raises(HiltResponseError, match="missing"):
        hilt._verify_attachments(output, request, response)


def test_attachment_apply_targets_and_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    output = tmp_path / "out"
    request, _ = hilt.create_request(
        output,
        step_id="files",
        gate_id="files",
        kind="files",
        title="Files",
        files=[
            HiltFileRequest(
                id="file",
                label="File",
                required=False,
                target="research/notes.md",
                allow_replace=False,
            )
        ],
    )
    attachment = hilt.save_attachment(
        output,
        request.interaction_id,
        request_id="file",
        filename="notes.md",
        data=b"hello",
        content_type="text/markdown",
    )
    response = hilt.respond(
        output,
        "",
        request.interaction_id,
        action="submit",
        attachments=[attachment],
    )
    manifest = hilt.apply_attachments(output, request, response[1])
    assert manifest[0]["target"].endswith("notes.md")
    assert (output / "research" / "notes.md").is_file()
    assert hilt.uploaded_attachments(output, request.interaction_id)

    with pytest.raises(HiltAttachmentError):
        hilt.apply_attachments(output, request, response[1])


def test_helpers_for_ids_and_paths(tmp_path: Path) -> None:
    assert hilt._slug("Hello World!") == "Hello-World"
    assert hilt._slug("!!!") == "item"
    assert hilt.make_interaction_id("step", "gate").startswith("hilt-step-gate")
    with pytest.raises(HiltResponseError):
        hilt.resolve_output_path(tmp_path, "../escape")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", "0")
    try:
        hilt._desktop_notify("title", "body")
    finally:
        monkeypatch.undo()


def test_invalid_ids_and_absolute_paths_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(HiltResponseError):
        hilt.interaction_dir(tmp_path, "../escape")
    with pytest.raises(HiltResponseError):
        hilt.artifact_for_path(tmp_path, "/etc/passwd")


def test_event_and_notification_write_failures_are_logged(
    tmp_path: Path, monkeypatch
) -> None:
    directory = tmp_path / "dir"
    directory.mkdir()
    monkeypatch.setattr(hilt, "_events_path", lambda target: directory)
    hilt._event(directory, "boom", {})
    monkeypatch.setattr(hilt, "_notifications_path", lambda target: directory)
    request = hilt.HiltRequest(
        interaction_id="hilt-x-y",
        step_id="x",
        gate_id="y",
        kind="question",
        title="Title",
    )
    hilt._notify_local(directory, request)


def test_desktop_notification_platforms(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(command, **kwargs):
        calls.append(command)
        return None

    monkeypatch.delenv("VIDEOWFLOW_DESKTOP_NOTIFICATIONS", raising=False)
    monkeypatch.setattr(hilt.sys, "platform", "linux")
    monkeypatch.setattr(hilt.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(hilt.subprocess, "run", run)
    hilt._desktop_notify("Title", "Body")
    assert calls and calls[0][0].endswith("notify-send")

    monkeypatch.setattr(hilt.sys, "platform", "darwin")
    hilt._desktop_notify("Title", "Body")
    assert calls[-1][0].endswith("osascript")

    monkeypatch.setattr(hilt.shutil, "which", lambda name: None)
    hilt._desktop_notify("Title", "Body")

    def boom(*args, **kwargs):
        raise OSError("no service")

    monkeypatch.setattr(hilt.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(hilt.subprocess, "run", boom)
    hilt._desktop_notify("Title", "Body")


def test_load_round_trip_handles_corrupt_payloads(tmp_path: Path) -> None:
    output = tmp_path / "out"
    request, _ = _request(output)
    assert hilt.load_request(output, "bad/id") is None
    assert hilt.load_response(output, "bad/id") is None

    directory = hilt.interaction_dir(output, request.interaction_id)
    (directory / "request.json").write_text("{not json", encoding="utf-8")
    assert hilt.load_request(output, request.interaction_id) is None
    (directory / "response.json").write_text("[1, 2]", encoding="utf-8")
    assert hilt.load_response(output, request.interaction_id) is None

    assert hilt.list_requests(tmp_path / "missing") == []
    (output / "hilt" / "stray.txt").write_text("x", encoding="utf-8")
    (output / "hilt" / "broken").mkdir()
    (output / "hilt" / "broken" / "request.json").write_text("{}", encoding="utf-8")
    assert all(
        item.interaction_id == request.interaction_id
        for item in hilt.list_requests(output)
    )


def test_answer_and_attachment_validation_edges(tmp_path: Path) -> None:
    from videoflow.domain.hilt import HiltResponse

    output = tmp_path / "out"
    request, _ = hilt.create_request(
        output,
        step_id="ask",
        gate_id="ask",
        kind="question",
        title="Ask",
        questions=[
            HiltQuestion(id="file", label="File", type="file", required=True),
            HiltQuestion(id="optional", label="Optional", type="text", required=False),
        ],
        files=[
            HiltFileRequest(id="a", label="A", required=True),
            HiltFileRequest(id="b", label="B", required=False),
        ],
    )
    with pytest.raises(HiltResponseError, match="needs a file"):
        hilt._validate_response(
            request,
            HiltResponse(interaction_id=request.interaction_id, action="submit"),
        )
    question = next(item for item in request.questions if item.id == "file")
    assert hilt._validate_answer(question, "anything") == "anything"
    with pytest.raises(HiltResponseError, match="already"):
        hilt._validate_response(
            request.model_copy(update={"status": "answered"}),
            HiltResponse(interaction_id=request.interaction_id, action="submit"),
        )

    response = HiltResponse(interaction_id=request.interaction_id)
    from videoflow.domain.hilt import HiltAttachment

    response.attachments = [
        HiltAttachment(
            request_id="a",
            original_name="a.txt",
            stored_path="a.txt",
            size_bytes=1,
            sha256="wrong",
        )
    ]
    directory = hilt.interaction_dir(output, request.interaction_id)
    (directory / "a.txt").write_bytes(b"x")
    with pytest.raises(HiltResponseError, match="checksum"):
        hilt._verify_attachments(output, request, response)
    response.attachments[0].size_bytes = 2
    with pytest.raises(HiltResponseError, match="changed"):
        hilt._verify_attachments(output, request, response)


def test_save_attachment_selection_and_collisions(tmp_path: Path) -> None:
    output = tmp_path / "out"
    request, _ = hilt.create_request(
        output,
        step_id="files",
        gate_id="files",
        kind="files",
        title="Files",
        questions=[HiltQuestion(id="qfile", label="Q", type="file")],
        files=[
            HiltFileRequest(id="only", label="Only", required=False),
            HiltFileRequest(
                id="strict",
                label="Strict",
                required=False,
                accept=[".md"],
                max_mb=1,
            ),
        ],
    )
    with pytest.raises(HiltResponseError):
        hilt.save_attachment(output, "missing", filename="x", data=b"x")
    with pytest.raises(HiltResponseError):
        hilt.save_attachment(
            output,
            request.interaction_id,
            request_id="nope",
            filename="x",
            data=b"x",
        )
    with pytest.raises(HiltResponseError, match="Choose"):
        hilt.save_attachment(
            output, request.interaction_id, filename="x", data=b"x"
        )
    with pytest.raises(HiltAttachmentError, match="accepted"):
        hilt.save_attachment(
            output,
            request.interaction_id,
            request_id="strict",
            filename="x.txt",
            data=b"x",
        )
    attachment = hilt.save_attachment(
        output,
        request.interaction_id,
        request_id="qfile",
        filename="notes.md",
        data=b"one",
    )
    again = hilt.save_attachment(
        output,
        request.interaction_id,
        request_id="qfile",
        filename="notes.md",
        data=b"one",
    )
    assert attachment.stored_path != again.stored_path


def test_apply_attachments_handles_directories_and_replace(
    tmp_path: Path,
) -> None:
    from videoflow.domain.hilt import HiltResponse

    output = tmp_path / "out"
    request, _ = hilt.create_request(
        output,
        step_id="files",
        gate_id="files",
        kind="files",
        title="Files",
        files=[
            HiltFileRequest(id="dir", label="Dir", required=False, target="docs"),
            HiltFileRequest(
                id="fixed",
                label="Fixed",
                required=False,
                target="fixed.txt",
                allow_replace=False,
            ),
        ],
    )
    first = hilt.save_attachment(
        output, request.interaction_id, request_id="dir", filename="a.txt", data=b"a"
    )
    second = hilt.save_attachment(
        output,
        request.interaction_id,
        request_id="fixed",
        filename="b.txt",
        data=b"b",
    )
    response = HiltResponse(
        interaction_id=request.interaction_id, attachments=[first, second]
    )
    manifest = hilt.apply_attachments(output, request, response)
    assert (output / "docs" / "a.txt").is_file()
    assert len(manifest) == 2
    with pytest.raises(HiltAttachmentError):
        hilt.apply_attachments(output, request, response)

    (output / "hilt" / request.interaction_id / "uploads.json").write_text(
        '{"attachments": "bad"}', encoding="utf-8"
    )
    assert hilt.uploaded_attachments(output, request.interaction_id) == []
    (output / "hilt" / request.interaction_id / "uploads.json").write_text(
        '{"attachments": [1, {"stored_path": "x"}]}', encoding="utf-8"
    )
    assert hilt.uploaded_attachments(output, request.interaction_id) == []
    assert hilt.unresolved_files(request, HiltResponse(interaction_id=request.interaction_id)) == []
