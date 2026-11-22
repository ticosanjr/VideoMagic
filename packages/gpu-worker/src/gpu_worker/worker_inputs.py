"""Input placeholder materialization and error formatting for GPU jobs."""

from __future__ import annotations

import re
from pathlib import Path

_INPUT_PLACEHOLDER = re.compile(r"__VF_INPUT_(\d+)__")


def _materialize_params(value: object, input_paths: list[Path]) -> object:
    """Replace ``__VF_INPUT_n__`` placeholders with materialized local paths."""

    if isinstance(value, str):
        match = _INPUT_PLACEHOLDER.fullmatch(value)
        if match is None:
            return value
        index = int(match.group(1))
        if 0 <= index < len(input_paths):
            return str(input_paths[index])
        return value
    if isinstance(value, dict):
        return {str(key): _materialize_params(item, input_paths) for key, item in value.items()}
    if isinstance(value, list):
        return [_materialize_params(item, input_paths) for item in value]
    return value


def _error_text(exc: Exception) -> str:
    message = str(exc).strip()
    text = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    return text[:2000]
