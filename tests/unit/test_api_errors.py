from __future__ import annotations

from videoflow.api.errors import status_for


def test_status_for_maps_typed_failures() -> None:
    assert status_for("path_not_allowed") == 403
    assert status_for("transcription_failed") == 502
    assert status_for("invalid_retake_ids") == 422
    assert status_for("invalid_transcript") == 422
    assert status_for("approval_required") == 409
    assert status_for("schema_too_new") == 409
    assert status_for("capability_unavailable") == 501
    assert status_for("not_implemented") == 501
    assert status_for("render_failed") == 500


def test_status_for_falls_back_to_bad_request() -> None:
    assert status_for("something_new") == 400
