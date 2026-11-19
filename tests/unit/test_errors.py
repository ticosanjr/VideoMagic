from videoflow.domain.errors import (
    CapabilityUnavailableError,
    InvalidOverrideError,
    InvalidPresetNameError,
    InvalidRetakeIdsError,
    JobAlreadyRunningError,
    MediaNotFoundError,
    ModuleBypassedError,
    NotImplementedCapabilityError,
    PathJailError,
    PresetNotFoundError,
    ProjectNotFoundError,
    TranscriptRequiredError,
    UnknownModuleError,
    UpstreamDirtyError,
    VideoFlowError,
)


def test_base_error_payload() -> None:
    error = VideoFlowError("boom")
    payload = error.to_dict()
    assert payload["ok"] is False
    assert payload["code"] == "videoflow_error"
    assert payload["error_code"] == "videoflow_error"
    assert payload["message"] == "boom"
    assert payload["failed_command"] == ""
    assert payload["stderr_tail"] == ""
    assert payload["fix_hint"]


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


def test_project_and_preset_errors_name_the_subject() -> None:
    assert ProjectNotFoundError("abc").to_dict()["code"] == "project_not_found"
    assert "abc" in str(ProjectNotFoundError("abc"))
    assert PresetNotFoundError("missing").to_dict()["code"] == "preset_not_found"
    assert MediaNotFoundError("/tmp/x").to_dict()["code"] == "media_not_found"
    assert UnknownModuleError("x").to_dict()["code"] == "unknown_module"
    assert InvalidOverrideError("x").code == "invalid_override"
    assert InvalidPresetNameError("x").code == "invalid_preset_name"
    assert TranscriptRequiredError("x").code == "transcript_required"


def test_unavailable_capability_payload_names_the_route() -> None:
    payload = CapabilityUnavailableError("module_run", "not yet").to_dict()
    assert payload["ok"] is False
    assert payload["code"] == "not_implemented"
    assert payload["error_code"] == "not_implemented"
    assert payload["message"] == "not yet"
    assert payload["capability"] == "module_run"
    assert "fix_hint" in payload
