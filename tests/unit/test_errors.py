from videoflow.domain.errors import (
    InvalidRetakeIdsError,
    JobAlreadyRunningError,
    ModuleBypassedError,
    NotImplementedCapabilityError,
    PathJailError,
    UpstreamDirtyError,
    VideoFlowError,
)


def test_base_error_payload() -> None:
    error = VideoFlowError("boom")
    assert error.to_dict() == {"ok": False, "code": "videoflow_error", "message": "boom"}


def test_not_implemented_payload_names_the_capability() -> None:
    payload = NotImplementedCapabilityError("videoflow_transcribe").to_dict()
    assert payload["code"] == "not_implemented"
    assert payload["tool"] == "videoflow_transcribe"


def test_upstream_payload_lists_ancestors() -> None:
    payload = UpstreamDirtyError("zooms", ["vad"]).to_dict()
    assert payload["ancestors"] == ["vad"]
    assert payload["code"] == "upstream_dirty"


def test_simple_errors_have_stable_codes() -> None:
    assert ModuleBypassedError("vad").code == "module_bypassed"
    assert JobAlreadyRunningError("vad").code == "job_already_running"
    assert PathJailError("/tmp/x").code == "path_not_allowed"
    assert InvalidRetakeIdsError([2, 1, 2]).unknown_ids == (1, 2)
