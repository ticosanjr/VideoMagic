"""One error envelope and one telemetry contract for every MCP tool.

The MCP boundary must never leak ``Error executing tool`` or a traceback to the
agent. This module turns every exception into the same JSON shape and fills the
execution telemetry with explicit defaults so ``job.execution`` is never ``{}``.
"""

from __future__ import annotations

import functools
import inspect
import subprocess
from collections.abc import Mapping
from difflib import get_close_matches
from typing import Any

from pydantic import ValidationError

from videoflow.domain.errors import VideoFlowError

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


def _suggest(name: str, candidates: list[str]) -> list[str]:
    return get_close_matches(str(name), candidates, n=3, cutoff=0.55)


def _invalid_keys(exc: BaseException) -> tuple[list[str], list[str]]:
    if isinstance(exc, ValidationError):
        keys = [
            str(error.get("loc", ["?"])[-1])
            for error in exc.errors()
            if error.get("loc")
        ]
        return sorted(set(keys)), []
    message = str(exc)
    marker = "unexpected keyword argument"
    if marker in message:
        key = message.rsplit("'", 2)[-2] if message.count("'") >= 2 else ""
        return ([key] if key else []), []
    if "missing" in message and "argument" in message:
        return [], []
    return [], []


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


def _hint(error_code: str, message: str) -> str:
    if error_code == "invalid_parameter":
        return "Use the exact parameter names from the tool schema."
    if "onnxruntime" in message.lower():
        return "Run Install/Repair in the Windows worker kit and check the ONNX runtime."
    if error_code == "gpu_worker_offline":
        return "Start the Windows GPU worker and confirm the LAN IP in Setup -> GPU."
    return "Retry once; if it persists, run doctor and attach the job log."


def error_envelope(
    exc: BaseException,
    *,
    func: Any | None = None,
) -> dict[str, Any]:
    """Return the single MCP error envelope for any exception."""

    if isinstance(exc, VideoFlowError):
        payload = dict(exc.to_dict())
        payload.setdefault("error_code", payload.get("code", "videoflow_error"))
        payload.setdefault("invalid_keys", [])
        payload.setdefault("did_you_mean", [])
        return payload

    invalid, did_you_mean = _invalid_keys(exc)
    if invalid and func is not None:
        did_you_mean = _suggest(invalid[0], _parameter_names(func))
    if isinstance(exc, ValidationError):
        error_code = "invalid_parameter"
        message = exc.errors()[0].get("msg", str(exc)) if exc.errors() else str(exc)
    elif isinstance(exc, TypeError):
        error_code = "invalid_parameter"
        message = str(exc)
    elif isinstance(exc, subprocess.CalledProcessError):
        error_code = "command_failed"
        message = f"command failed with exit code {exc.returncode}"
    else:
        error_code = "internal_error"
        message = str(exc) or exc.__class__.__name__

    command, stderr = _command_details(exc)
    return {
        "ok": False,
        "error_code": error_code,
        "code": error_code,
        "message": message,
        "invalid_keys": invalid,
        "did_you_mean": did_you_mean,
        "failed_command": command,
        "stderr_tail": stderr,
        "fix_hint": _hint(error_code, message),
    }


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
                result = await func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - MCP boundary
                return error_envelope(exc, func=func)
            return normalize_execution(result)

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - MCP boundary
            return error_envelope(exc, func=func)
        return normalize_execution(result)

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
    "normalize_execution",
]
