"""One error envelope and one telemetry contract for every MCP tool.

The MCP boundary must never leak ``Error executing tool`` or a traceback to the
agent. This module turns every exception into the same JSON shape and fills the
execution telemetry with explicit defaults so ``job.execution`` is never ``{}``.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import subprocess
import traceback
from collections.abc import Mapping
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from videoflow.domain.errors import VideoFlowError

TRACKED_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "vf_ingest",
        "vf_run",
        "vf_decupage",
        "vf_scenes",
        "vf_shorts",
        "vf_export",
        "vf_qa",
        "vf_fx_depth",
        "vf_fx_parallax",
        "vf_fx_motion",
        "vf_fx_capture",
    }
)

# These tools already own a JobManager row. The guard must not create a second
# one while the real job is running in SQLite.
_JOB_OWNED_MCP_TOOLS: frozenset[str] = frozenset(
    {"vf_ingest", "vf_run", "vf_decupage", "vf_shorts"}
)

_EXECUTION_DEFAULTS: dict[str, Any] = {
    "execution_node": "local",
    "device": "cpu",
    "model": "",
    "vram_peak_mb": 0,
    "frames": 0,
    "in_duration_sec": 0.0,
    "out_duration_sec": 0.0,
    "rtf": 0.0,
    "cache_hit": False,
    "degraded": False,
    "degraded_reason": "",
}


def _parameter_names(func: Any) -> list[str]:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return []
    return [
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind
        in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }
    ]


@functools.lru_cache(maxsize=512)
def _accepts_project_id(func: Any) -> bool:
    try:
        return "project_id" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _bound_arguments(
    func: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> inspect.BoundArguments | None:
    try:
        return inspect.signature(func).bind_partial(*args, **kwargs)
    except (TypeError, ValueError):
        return None


def _tracking_plan(
    func: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[Any, Any]:
    """Return the origin context and optional MCP job tracker for one tool."""

    name = str(getattr(func, "__name__", ""))
    if name not in TRACKED_MCP_TOOLS:
        return contextlib.nullcontext(), None
    bound = _bound_arguments(func, args, kwargs)
    project_id = ""
    source = ""
    output = ""
    if bound is not None:
        project_id = str(bound.arguments.get("project_id") or "")
        source = str(
            bound.arguments.get("source")
            or bound.arguments.get("input_path")
            or ""
        )
        output = str(bound.arguments.get("output") or "")
    from videoflow.application.jobs import job_origin, track_mcp_job

    context = job_origin("mcp")
    owned = name in _JOB_OWNED_MCP_TOOLS
    if name == "vf_export" and bound is not None:
        action = str(bound.arguments.get("action") or "bundle")
        owned = action in {"render", "roundtrip"}
    if owned:
        return context, None
    return context, track_mcp_job(
        name,
        project_id=project_id,
        source=source,
        output=output,
    )


def _canonical_project_call(
    func: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Resolve slug/UUID before the tool body so every tool shares one identity."""

    if not _accepts_project_id(func):
        return args, kwargs
    try:
        bound = inspect.signature(func).bind_partial(*args, **kwargs)
    except (TypeError, ValueError):
        return args, kwargs
    raw = bound.arguments.get("project_id")
    if not isinstance(raw, str) or not raw.strip():
        return args, kwargs
    try:
        from videoflow.application.projects import canonical_project_id
    except Exception:  # noqa: BLE001 - the tool reports its own import failure
        return args, kwargs
    canonical = canonical_project_id(raw)
    if canonical == raw:
        return args, kwargs
    bound.arguments["project_id"] = canonical
    return bound.args, bound.kwargs


def _suggest(keys: list[str], candidates: list[str]) -> dict[str, str]:
    """Map each unknown key to its closest valid parameter, if any."""

    suggestions: dict[str, str] = {}
    valid = set(candidates)
    for key in keys:
        if key in valid:
            continue
        matches = get_close_matches(str(key), candidates, n=1, cutoff=0.55)
        if matches:
            suggestions[str(key)] = matches[0]
    return suggestions


def suggest_parameters(
    keys: list[str], candidates: list[str]
) -> dict[str, str]:
    """Return close-match suggestions for unknown tool parameters."""

    return _suggest(keys, candidates)


def _invalid_keys(exc: BaseException) -> list[str]:
    if isinstance(exc, ValidationError):
        keys = [
            str(error.get("loc", ["?"])[-1])
            for error in exc.errors()
            if error.get("loc")
        ]
        return sorted(set(keys))
    message = str(exc)
    marker = "unexpected keyword argument"
    if marker in message:
        key = message.rsplit("'", 2)[-2] if message.count("'") >= 2 else ""
        return [key] if key else []
    return []


def _command_details(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, subprocess.CalledProcessError):
        command = exc.cmd
        if isinstance(command, (list, tuple)):
            command = " ".join(str(item) for item in command)
        stderr = exc.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return str(command or ""), str(stderr or "")[-4000:]
    command = str(getattr(exc, "command", "") or getattr(exc, "cmd", "") or "")
    stderr = getattr(exc, "stderr", "") or ""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    return command, str(stderr)[-4000:]


def _expected_fields(func: Any | None) -> dict[str, str]:
    if func is None:
        return {}
    fields: dict[str, str] = {}
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return {}
    for name, parameter in signature.parameters.items():
        if parameter.kind not in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }:
            continue
        annotation = parameter.annotation
        fields[name] = getattr(annotation, "__name__", str(annotation))
    return fields


def _hint(error_code: str, message: str) -> str:
    if error_code == "invalid_params":
        return "Use the exact parameter names from the tool schema."
    if "onnxruntime" in message.lower():
        return "Run Install/Repair in the Windows worker kit and check the ONNX runtime."
    if error_code == "gpu_worker_offline":
        return "Start the Windows GPU worker and confirm the LAN IP in Setup -> GPU."
    return "Retry once; if it persists, run doctor and attach the job log."


def _stack_tail(exc: BaseException, limit: int = 5) -> list[str]:
    frames = traceback.extract_tb(exc.__traceback__)
    return [
        f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}"
        for frame in frames[-limit:]
    ]


def _last_frame(exc: BaseException) -> str:
    frames = _stack_tail(exc, limit=1)
    return frames[0] if frames else "unknown frame"


def error_envelope(
    exc: BaseException,
    *,
    func: Any | None = None,
) -> dict[str, Any]:
    """Return the single MCP error envelope for any exception."""

    last_frame = _last_frame(exc)
    stack_tail = _stack_tail(exc)
    if isinstance(exc, VideoFlowError):
        payload = dict(exc.to_dict())
        payload["error_code"] = (
            payload.get("error_code")
            or getattr(exc, "code", None)
            or type(exc).__name__.lower()
        )
        payload["code"] = payload.get("code") or payload["error_code"]
        payload["message"] = str(payload.get("message") or "").strip() or (
            f"{type(exc).__name__} at {last_frame}"
        )
        payload.setdefault("invalid_keys", [])
        payload.setdefault("did_you_mean", {})
        payload.setdefault("last_frame", last_frame)
        payload.setdefault("stack_tail", stack_tail)
        return payload

    invalid = _invalid_keys(exc)
    did_you_mean = (
        _suggest(invalid, _parameter_names(func)) if invalid and func else {}
    )
    if isinstance(exc, ValidationError):
        error_code = "invalid_params"
        message = exc.errors()[0].get("msg", str(exc)) if exc.errors() else str(exc)
    elif isinstance(exc, TypeError):
        error_code = "invalid_params"
        message = str(exc).strip() or f"{type(exc).__name__} at {last_frame}"
    elif isinstance(exc, subprocess.CalledProcessError):
        error_code = "command_failed"
        message = f"command failed with exit code {exc.returncode}"
    else:
        error_code = getattr(exc, "code", None) or type(exc).__name__.lower()
        message = str(exc).strip() or f"{type(exc).__name__} at {last_frame}"

    command, stderr = _command_details(exc)
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
        "code": error_code,
        "message": message,
        "invalid_keys": invalid,
        "did_you_mean": did_you_mean,
        "failed_command": command,
        "stderr_tail": stderr,
        "fix_hint": _hint(error_code, message),
        "last_frame": last_frame,
        "stack_tail": stack_tail,
    }
    if isinstance(exc, ValidationError):
        expected = _expected_fields(func)
        if expected:
            payload["expected_fields"] = expected
            payload["fix_hint"] = (
                payload["fix_hint"]
                + " Expected fields: "
                + ", ".join(f"{key}: {value}" for key, value in expected.items())
            )
    return payload


MAX_LIST_ITEMS = 30
_PRESERVE_LISTS = frozenset({"capabilities"})

DEFAULT_NEXT_STEP: dict[str, str] = {
    "vf_project": "Run vf_session_brief to inspect the project and choose the next step.",
    "vf_session_brief": "Choose the style and workflow, then run vf_ingest.",
    "vf_ingest": "Run vf_transcript, then vf_decupage.",
    "vf_transcript": "Run vf_decupage or request more transcript ranges.",
    "vf_decupage": "Review the beat map, then apply it with vf_timeline.",
    "vf_timeline": "Preview the result with vf_preview.",
    "vf_preview": "Request human review or continue with vf_qa.",
    "vf_qa": "Fix the reported defects and rerun vf_qa, then export.",
    "vf_export": "Verify the exported files and run vf_qa_final.",
    "vf_jobs": "Poll with vf_jobs or continue the workflow when the job is done.",
    "vf_curation": "Inform the board URL and wait for the human decision.",
}


def _truncate_lists(value: Any) -> Any:
    """Truncate long lists and make the omission explicit to the agent."""

    if not isinstance(value, dict):
        return value
    truncated: dict[str, int] = {}
    for key, item in value.items():
        if (
            isinstance(item, list)
            and key not in _PRESERVE_LISTS
            and len(item) > MAX_LIST_ITEMS
        ):
            value[key] = item[:MAX_LIST_ITEMS]
            truncated[key] = len(item)
        elif isinstance(item, dict):
            _truncate_lists(item)
    if truncated:
        value["truncated"] = True
        value["truncated_fields"] = truncated
        value.setdefault("total_count", next(iter(truncated.values())))
        value.setdefault("next_offset", MAX_LIST_ITEMS)
        value.setdefault("hint", "Use pagination/query parameters to read more.")
    return value


def normalize_error_hint(payload: Any) -> Any:
    """Make unknown actions and invalid params self-correcting for agents."""

    if not isinstance(payload, dict) or payload.get("ok") is not False:
        return payload
    hint = str(payload.get("fix_hint") or "").strip()
    valid = payload.get("valid_actions")
    if isinstance(valid, (list, tuple)) and valid:
        listing = ", ".join(str(item) for item in valid)
        if listing.casefold() not in hint.casefold():
            payload["fix_hint"] = (hint + f" Valid actions: {listing}.").strip()
    expected = payload.get("expected_fields")
    if isinstance(expected, dict) and expected:
        listing = ", ".join(f"{key}: {value}" for key, value in expected.items())
        if listing.casefold() not in str(payload.get("fix_hint") or "").casefold():
            payload["fix_hint"] = (
                str(payload.get("fix_hint") or "")
                + f" Expected fields: {listing}."
            ).strip()
    return payload


def normalize_success(payload: Any, tool_name: str = "") -> Any:
    """Add the next-step contract and compact long lists on successful tools."""

    if not isinstance(payload, dict) or payload.get("ok") is False:
        return payload
    payload.setdefault(
        "_next_step",
        DEFAULT_NEXT_STEP.get(
            tool_name,
            "Continue with the next workflow step or inspect the returned payload.",
        ),
    )
    return _truncate_lists(payload)


def _fill_execution(value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key, default in _EXECUTION_DEFAULTS.items():
        value.setdefault(key, default)


def normalize_execution(payload: Any) -> Any:
    """Ensure ``job.execution`` is present and never an empty object."""

    if not isinstance(payload, dict):
        return payload
    execution = payload.get("execution")
    if execution is not None:
        if not isinstance(execution, dict):
            execution = {}
            payload["execution"] = execution
        _fill_execution(execution)
    job = payload.get("job")
    if isinstance(job, dict):
        if not isinstance(job.get("execution"), dict):
            job["execution"] = {}
        _fill_execution(job["execution"])
    return payload


def mcp_tool_guard(func: Any) -> Any:
    """Wrap a sync or async tool with the canonical envelope and telemetry."""

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                call_args, call_kwargs = _canonical_project_call(func, args, kwargs)
                context, tracker = _tracking_plan(func, call_args, call_kwargs)
                with context:
                    if tracker is None:
                        result = await func(*call_args, **call_kwargs)
                    else:
                        with tracker:
                            result = await func(*call_args, **call_kwargs)
                            tracker.finish(result)
            except Exception as exc:  # noqa: BLE001 - MCP boundary
                return normalize_error_hint(error_envelope(exc, func=func))
            return normalize_error_hint(
                normalize_execution(normalize_success(result, func.__name__))
            )

        async_wrapper.__mcp_guarded__ = True  # type: ignore[attr-defined]
        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            call_args, call_kwargs = _canonical_project_call(func, args, kwargs)
            context, tracker = _tracking_plan(func, call_args, call_kwargs)
            with context:
                if tracker is None:
                    result = func(*call_args, **call_kwargs)
                else:
                    with tracker:
                        result = func(*call_args, **call_kwargs)
                        tracker.finish(result)
        except Exception as exc:  # noqa: BLE001 - MCP boundary
            return normalize_error_hint(error_envelope(exc, func=func))
        return normalize_error_hint(
            normalize_execution(normalize_success(result, func.__name__))
        )

    wrapper.__mcp_guarded__ = True  # type: ignore[attr-defined]
    return wrapper


def fill_execution(metadata: Mapping[str, Any] | None, **values: Any) -> dict[str, Any]:
    """Build an execution dict from defaults plus measured values."""

    payload = dict(_EXECUTION_DEFAULTS)
    if metadata:
        for key in _EXECUTION_DEFAULTS:
            if key in metadata:
                payload[key] = metadata[key]
    payload.update(values)
    return payload


__all__ = [
    "error_envelope",
    "fill_execution",
    "mcp_tool_guard",
    "DEFAULT_NEXT_STEP",
    "MAX_LIST_ITEMS",
    "normalize_execution",
    "normalize_success",
    "suggest_parameters",
]
