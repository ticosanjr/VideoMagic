import json
from pathlib import Path

import pytest

from videoflow.application.portable import run_portable
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.errors import IngestError
from videoflow.domain.state import MediaInfo


class FakeAdapter:
    def __init__(self, speech: list[tuple[int, int]] | None = None) -> None:
        self.speech = speech if speech is not None else [(0, 48000), (96000, 144000)]

    def probe(self, path: Path) -> MediaInfo:
        return MediaInfo(
            source_path=str(path),
            duration_frames=90,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        )

    def extract_pcm(self, source: Path, destination: Path, *, sample_rate: int = 16000) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"RIFF")
        assert sample_rate == 48000
        return destination

    def pcm_digest(self, path: Path) -> str:
        return "digest"

    def detect_speech(
        self,
        wav_path: Path,
        *,
        duration_samples: int,
        sample_rate: int,
        noise_db: float = -30.0,
        min_silence_ms: int = 400,
        min_speech_ms: int = 100,
    ) -> list[tuple[int, int]]:
        return self.speech


def test_portable_pipeline_writes_state_report_and_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    result = run_portable(
        source,
        tmp_path / "project",
        jl=JlCutsConfig(enable_j_cuts=True),
        zooms=ZoomsConfig(mode="alternate_cuts"),
        adapter=FakeAdapter(),  # type: ignore[arg-type]
    )
    assert result.state.media_info is not None
    assert len(result.state.video_segments) == 2
    assert len(result.state.vad_intervals) == 2
    assert set(result.artifacts) == {"resolve", "premiere", "kdenlive"}
    assert result.state_path.is_file()
    assert result.report_path.is_file()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["pcm_sha256"] == "digest"
    assert report["video_segment_count"] == 2
    assert report["artifacts"]["resolve"].endswith("timeline.fcpxml")


def test_transcript_culls_exact_repeats_and_updates_state(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = tmp_path / "subs.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nSame line.\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\nSame line.\n",
        encoding="utf-8",
    )
    result = run_portable(
        source,
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        transcript_path=transcript,
        cull_retakes=True,
    )
    assert len(result.state.transcript) == 2
    assert result.state.retake_culls == [0]
    assert len(result.state.video_segments) == 1
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["transcript_sentence_count"] == 2
    assert report["retake_cull_count"] == 1


def test_portable_pipeline_reports_stages_logs_and_targets(tmp_path: Path) -> None:
    from videoflow.application.telemetry import JobTelemetry

    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    telemetry = JobTelemetry()
    logs: list[tuple[str, str, str]] = []
    result = run_portable(
        source,
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        telemetry=telemetry,
        log=lambda module, level, message: (
            logs.append((module, level, message)),
            telemetry.log(module, level, message),
        ),
        targets=("resolve",),
    )
    stages = {item["id"]: item for item in telemetry.stages()}
    assert {"ingest", "vad", "jl_cuts", "zooms", "export"} <= set(stages)
    assert stages["ingest"]["status"] == "succeeded"
    assert stages["ingest"]["started_at"]
    assert stages["ingest"]["duration_ms"] is not None
    assert set(result.artifacts) == {"resolve"}
    assert any("PCM" in row[2] for row in logs)
    assert telemetry.log_count() > 0


def test_portable_pipeline_fails_when_no_speech_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    with pytest.raises(IngestError, match="No speech"):
        run_portable(
            source,
            tmp_path / "project",
            adapter=FakeAdapter(speech=[]),  # type: ignore[arg-type]
        )
