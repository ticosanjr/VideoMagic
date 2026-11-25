"""Validation edges for domain models, migrations, and transcripts."""

from __future__ import annotations

from pathlib import Path

import pytest

from videoflow.domain.config import ShortsConfig, ZoomsConfig
from videoflow.domain.errors import (
    ProjectStateError,
    RecipeError,
    StepExecutionError,
    TranscriptError,
)
from videoflow.domain.migrations import migrate_project_state, migrate_recipe
from videoflow.domain.transcript import parse_srt, parse_srt_file


def test_zoom_scale_window_is_validated() -> None:
    with pytest.raises(ValueError, match="min_scale exceeds max_scale"):
        ZoomsConfig(min_scale=1.08, max_scale=1.0)


def test_shorts_window_rejects_inverted_clip_counts() -> None:
    with pytest.raises(ValueError, match="min_clips exceeds"):
        ShortsConfig(min_clips=3, max_clips_to_generate=1)


def test_step_error_serialises_its_step_id() -> None:
    payload = StepExecutionError("render", "boom").to_dict()

    assert payload["code"] == "step_failed"
    assert payload["step_id"] == "render"
    assert payload["message"] == "Step render: boom"


def test_migrations_reject_non_object_roots() -> None:
    with pytest.raises(ProjectStateError, match="root must be a JSON object"):
        migrate_project_state([])  # type: ignore[arg-type]
    with pytest.raises(RecipeError, match="root must be a JSON object"):
        migrate_recipe([])  # type: ignore[arg-type]


def test_srt_without_timecodes_is_rejected() -> None:
    with pytest.raises(TranscriptError, match="missing timecode"):
        parse_srt("just text\n\nmore text", sample_rate=48000)


def test_srt_file_reading_errors_are_actionable(tmp_path: Path) -> None:
    with pytest.raises(TranscriptError, match="cannot read"):
        parse_srt_file(tmp_path / "missing.srt", sample_rate=48000)

    empty = tmp_path / "empty.srt"
    empty.write_text("   \n", encoding="utf-8")
    with pytest.raises(TranscriptError, match="empty"):
        parse_srt_file(empty, sample_rate=48000)


def test_srt_invalid_timestamps_are_rejected() -> None:
    with pytest.raises(TranscriptError, match="missing timecode"):
        parse_srt(
            "1\nnot-a-time\nignored\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\nKept.\n",
            sample_rate=48000,
        )

    sentences = parse_srt("1\n00:00:01,000 --> 00:00:02,000\nKept.\n", 48000)
    assert [sentence.text for sentence in sentences] == ["Kept."]
