"""Shared validation, bounds and stock request helpers."""

from __future__ import annotations

import math

from .errors import InvalidRequestError

ORIENTATIONS = {"landscape", "portrait", "square"}


def _require_query(query: str) -> str:
    value = str(query or "").strip()
    if not value:
        raise InvalidRequestError("query must not be empty.")
    return value


def _check_orientation(value: str) -> str:
    normalized = str(value or "landscape").strip().lower()
    if normalized not in ORIENTATIONS:
        raise InvalidRequestError(
            f"orientation must be one of {sorted(ORIENTATIONS)}, got {value!r}."
        )
    return normalized


def _bounded_int(value: int, *, name: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidRequestError(f"{name} must be an integer.") from exc
    if not minimum <= number <= maximum:
        raise InvalidRequestError(f"{name} must be between {minimum} and {maximum}, got {number}.")
    return number


def _bounded_float(
    value: float,
    *,
    name: str,
    minimum: float,
    maximum: float | None = None,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidRequestError(f"{name} must be a number.") from exc
    if not math.isfinite(number) or number < minimum:
        raise InvalidRequestError(f"{name} must be a finite number >= {minimum}.")
    if maximum is not None and number > maximum:
        raise InvalidRequestError(f"{name} must be <= {maximum}.")
    return number


def _clip(start_time: float, end_time: float) -> dict[str, float]:
    return {"start": round(start_time, 3), "end": round(end_time, 3)}
