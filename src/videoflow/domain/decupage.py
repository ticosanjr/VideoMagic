"""Agent-facing decupage contracts.

Timestamps stay in integer samples and frames. Seconds are display fields only;
an LLM receives ``asu_id`` and word indexes, never timestamps.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AsuWord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idx: int = Field(ge=0)
    w: str
    start_sample: int = Field(ge=0)
    end_sample: int = Field(ge=0)
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    p: float = Field(default=0.0, ge=0.0, le=1.0)


class Asu(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asu_id: str
    start_sample: int = Field(ge=0)
    end_sample: int = Field(ge=0)
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    pause_before: float = Field(default=0.0, ge=0.0)
    pause_after: float = Field(default=0.0, ge=0.0)
    text: str
    avg_word_prob: float = Field(default=0.0, ge=0.0, le=1.0)
    rms_mean_db: float = -120.0
    speech_rate_wps: float = Field(default=0.0, ge=0.0)
    retake_group_id: str = ""
    has_stutter_candidate: bool = False
    noise_events: list[dict[str, Any]] = Field(default_factory=list)
    words: list[AsuWord] = Field(default_factory=list)


class AsuReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    sample_rate: int = Field(gt=0)
    count: int = Field(ge=0)
    asus: list[Asu] = Field(default_factory=list)
    source: str = "transcript"


class AsuDecision(BaseModel):
    """One LLM decision. Timestamps are never accepted from the model."""

    model_config = ConfigDict(extra="forbid")

    asu_id: str
    action: Literal[
        "KEEP",
        "REMOVE",
        "REMOVE_RETAKE",
        "REMOVE_NOISE",
        "REMOVE_FILLER",
        "TRIM_WORDS",
        "QUARANTINE",
        "REVIEW",
        "RESTORE",
    ]
    category: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    remove_word_indices: list[int] = Field(default_factory=list)
    reason: str = ""


class DecupageWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_id: str
    asu_ids: list[str] = Field(default_factory=list)
    asus: list[dict[str, Any]] = Field(default_factory=list)
    word_count: int = Field(default=0, ge=0)


class DecupageSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_sample: int = Field(ge=0)
    end_sample: int = Field(ge=0)
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    valley_rms_dbfs: float | None = None
    pad_clamped_by_noise: bool = False
    pre_roll_ms: float = 0.0
    post_roll_ms: float = 0.0


class DecupageCut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_sample: int = Field(ge=0)
    end_sample: int = Field(ge=0)
    reason: str = "remove"
    asu_id: str = ""
    needs_broll_or_punch_in: bool = False


class DecupageJoin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_sample: int = Field(ge=0)
    duration_ms: float = Field(default=18.0, ge=0.0)
    curve: str = "equal_power"


class DecupagePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    sample_rate: int = Field(gt=0)
    fps_num: int = Field(gt=0)
    fps_den: int = Field(gt=0)
    source_duration_samples: int = Field(ge=0)
    active_spans: list[DecupageSpan] = Field(default_factory=list)
    cuts: list[DecupageCut] = Field(default_factory=list)
    joins: list[DecupageJoin] = Field(default_factory=list)
    review_flags: list[dict[str, str]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
