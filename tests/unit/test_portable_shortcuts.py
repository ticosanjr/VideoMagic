"""Portable pipeline shortcuts: cancellation, boosts, reframing, and overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.test_portable import FakeAdapter
from videoflow.application.portable import run_portable
from videoflow.domain.config import ShortsConfig
from videoflow.domain.errors import (
    IngestError,
    InvalidRetakeIdsError,
    JobCancelledError,
)
from videoflow.domain.state import ManualOverride, Sentence

RATE = 48000


def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.mp4"
    path.write_bytes(b"fixture")
    return path


def transcript() -> list[Sentence]:
    return [
        Sentence(id=0, start_sample=0, end_sample=RATE, text="First sentence here."),
        Sentence(id=1, start_sample=2 * RATE, end_sample=3 * RATE, text="Second sentence."),
    ]


class FakeTelemetry:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.finished: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.cancelled: list[str] = []
        self.active = "ingest"

    def start(self, stage_id: str, *_args: object) -> None:
        self.started.append(stage_id)

    def update(self, *_args: object) -> None:
        return None

    def finish(self, stage_id: str, _message: str = "") -> None:
        self.finished.append(stage_id)

    def fail(self, stage_id: str, message: str) -> None:
        self.failed.append((stage_id, message))

    def cancel(self, stage_id: str) -> None:
        self.cancelled.append(stage_id)

    def active_stage(self) -> str | None:
        return self.active


def test_cancellation_before_ingest_stops_the_run(tmp_path: Path) -> None:
    with pytest.raises(JobCancelledError):
        run_portable(
            source(tmp_path),
            tmp_path / "project",
            adapter=FakeAdapter(),  # type: ignore[arg-type]
            vad_engine="ffmpeg",
            should_cancel=lambda: True,
        )


def test_cancellation_marks_the_active_telemetry_stage(tmp_path: Path) -> None:
    telemetry = FakeTelemetry()
    checks = {"count": 0}

    def cancel_on_second_check() -> bool:
        checks["count"] += 1
        return checks["count"] > 1

    with pytest.raises(JobCancelledError):
        run_portable(
            source(tmp_path),
            tmp_path / "project",
            adapter=FakeAdapter(),  # type: ignore[arg-type]
            vad_engine="ffmpeg",
            should_cancel=cancel_on_second_check,
            telemetry=telemetry,  # type: ignore[arg-type]
        )

    assert telemetry.cancelled == ["ingest"]


def test_build_timeline_failure_marks_telemetry(tmp_path: Path, monkeypatch) -> None:
    telemetry = FakeTelemetry()

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("timeline blew up")

    monkeypatch.setattr("videoflow.application.portable.build_timeline", fail)

    with pytest.raises(RuntimeError, match="timeline blew up"):
        run_portable(
            source(tmp_path),
            tmp_path / "project",
            adapter=FakeAdapter(),  # type: ignore[arg-type]
            vad_engine="ffmpeg",
            telemetry=telemetry,  # type: ignore[arg-type]
        )

    assert ("ingest", "timeline blew up") in telemetry.failed


def test_shorts_without_a_transcript_fail(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="Shorts require a transcript"):
        run_portable(
            source(tmp_path),
            tmp_path / "project",
            adapter=FakeAdapter(),  # type: ignore[arg-type]
            vad_engine="ffmpeg",
            shorts=True,
            shorts_min_sec=1,
            shorts_max_sec=3,
        )


def test_scene_and_energy_boost_failures_become_warnings(
    tmp_path: Path, monkeypatch
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise IngestError("analysis unavailable")

    monkeypatch.setattr("videoflow.application.portable.detect_scene_changes", fail)
    monkeypatch.setattr("videoflow.application.portable.detect_audio_energy", fail)

    result = run_portable(
        source(tmp_path),
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        shorts=True,
        shorts_config=ShortsConfig(
            target_duration_min_sec=1,
            target_duration_max_sec=3,
            min_clips=1,
            max_clips_to_generate=1,
            scene_change_boost=True,
            audio_energy_boost=True,
        ),
        transcript_sentences=transcript(),
    )

    assert any("Scene analysis skipped" in warning for warning in result.warnings)
    assert any("Audio energy analysis skipped" in warning for warning in result.warnings)


def test_reframing_tracks_focus_and_reports_a_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "videoflow.application.portable.track_focus_x",
        lambda *_a, **_k: (0.3, "motion_tracking"),
    )

    result = run_portable(
        source(tmp_path),
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        shorts=True,
        shorts_config=ShortsConfig(
            target_duration_min_sec=1,
            target_duration_max_sec=3,
            min_clips=1,
            max_clips_to_generate=1,
            reframe_mode="face_tracking",
        ),
        transcript_sentences=transcript(),
    )

    assert any("used motion_tracking" in warning for warning in result.warnings)
    assert result.shorts[0]["crop_focus_x"] == 0.3


def test_unknown_manual_overrides_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidRetakeIdsError):
        run_portable(
            source(tmp_path),
            tmp_path / "project",
            adapter=FakeAdapter(),  # type: ignore[arg-type]
            vad_engine="ffmpeg",
            cull_retakes=True,
            overrides=[ManualOverride(sentence_id=99, action="discard")],
            transcript_sentences=transcript(),
        )


def test_discarding_every_sentence_fails(tmp_path: Path) -> None:
    overrides = [
        ManualOverride(sentence_id=0, action="discard"),
        ManualOverride(sentence_id=1, action="discard"),
    ]

    with pytest.raises(IngestError, match="removed all speech"):
        run_portable(
            source(tmp_path),
            tmp_path / "project",
            adapter=FakeAdapter(),  # type: ignore[arg-type]
            vad_engine="ffmpeg",
            cull_retakes=True,
            overrides=overrides,
            transcript_sentences=transcript(),
        )
