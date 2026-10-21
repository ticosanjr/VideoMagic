import json
from pathlib import Path

import pytest

from videoflow.application.portable import run_portable
from videoflow.domain.config import JlCutsConfig, ZoomsConfig
from videoflow.domain.errors import IngestError
from videoflow.domain.state import ManualOverride, MediaInfo


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
        assert sample_rate in {16000, 48000}
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

    def render_short(
        self,
        source: Path,
        pieces: object,
        destination: Path,
        *,
        sample_rate: int,
        ass_path: Path | None = None,
        width: int = 1080,
        height: int = 1920,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"mp4")
        return destination


def test_portable_pipeline_writes_state_report_and_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    result = run_portable(
        source,
        tmp_path / "project",
        jl=JlCutsConfig(enable_j_cuts=True),
        zooms=ZoomsConfig(mode="alternate_cuts"),
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
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
    assert report["vad_engine"] == "ffmpeg"


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
        vad_engine="ffmpeg",
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
        vad_engine="ffmpeg",
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


def test_manual_discard_and_keep_override_culls(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = tmp_path / "subs.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nSame line.\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\nSame line.\n",
        encoding="utf-8",
    )
    kept = run_portable(
        source,
        tmp_path / "keep",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcript_path=transcript,
        cull_retakes=True,
        overrides=[ManualOverride(sentence_id=0, action="keep")],
    )
    assert kept.state.retake_culls == []
    assert len(kept.state.video_segments) == 2
    assert kept.state.manual_overrides[0].action == "keep"

    discarded = run_portable(
        source,
        tmp_path / "discard",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcript_path=transcript,
        overrides=[ManualOverride(sentence_id=0, action="discard")],
    )
    assert discarded.state.retake_culls == [0]
    assert len(discarded.state.video_segments) == 1


def test_portable_pipeline_can_use_an_asr_client(tmp_path: Path) -> None:
    from videoflow.domain.state import Sentence

    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")

    class Asr:
        def transcribe(self, wav_path: Path, sample_rate: int) -> list[Sentence]:
            return [
                Sentence(id=0, start_sample=0, end_sample=48000, text="Asr line one"),
                Sentence(id=1, start_sample=96000, end_sample=144000, text="Asr line two"),
            ]

    result = run_portable(
        source,
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcribe=True,
        asr_client=Asr(),
        cull_retakes=False,
    )
    assert result.transcript_source == "asr"
    assert len(result.state.transcript) == 2
    assert result.to_dict()["transcript_source"] == "asr"


def test_portable_pipeline_uses_local_whisper_without_an_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.application import portable
    from videoflow.domain.config import TranscribeConfig
    from videoflow.domain.state import Sentence

    monkeypatch.delenv("VIDEOWFLOW_ASR_BASE_URL", raising=False)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    seen: dict[str, object] = {}

    class Local:
        def __init__(self, **kwargs: object) -> None:
            seen.update(kwargs)

        def transcribe(self, wav_path: Path, sample_rate: int) -> list[Sentence]:
            seen["wav"] = wav_path
            seen["sample_rate"] = sample_rate
            return [
                Sentence(id=0, start_sample=0, end_sample=48000, text="Local line one"),
                Sentence(id=1, start_sample=96000, end_sample=144000, text="Local line two"),
            ]

    monkeypatch.setattr(portable, "WhisperCliAdapter", Local)
    result = run_portable(
        source,
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcribe=True,
        whisper_model=tmp_path / "model.bin",
        transcribe_config=TranscribeConfig(engine="whisper.cpp"),
        cull_retakes=False,
    )
    assert result.transcript_source == "whisper"
    assert len(result.state.transcript) == 2
    assert seen["sample_rate"] == 48000
    assert Path(str(seen["wav"])).name == "transcribe.wav"
    assert seen["model"] == tmp_path / "model.bin"
    assert result.to_dict()["transcript_source"] == "whisper"


def test_portable_pipeline_auto_prefers_faster_whisper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.application import portable
    from videoflow.domain.state import Sentence

    monkeypatch.delenv("VIDEOWFLOW_ASR_BASE_URL", raising=False)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    seen: dict[str, object] = {}

    class Faster:
        @staticmethod
        def available(*args: object, **kwargs: object) -> bool:
            return True

        def __init__(self, **kwargs: object) -> None:
            seen.update(kwargs)

        def transcribe(self, wav_path: Path, sample_rate: int) -> list[Sentence]:
            seen["wav"] = wav_path
            return [
                Sentence(id=0, start_sample=0, end_sample=48000, text="Faster line one"),
                Sentence(id=1, start_sample=96000, end_sample=144000, text="Faster line two"),
            ]

    monkeypatch.setattr(portable, "FasterWhisperAdapter", Faster)
    result = run_portable(
        source,
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcribe=True,
        faster_whisper_model=tmp_path / "model",
        cull_retakes=False,
    )
    assert result.transcript_source == "faster-whisper"
    assert len(result.state.transcript) == 2
    assert seen["model"] == tmp_path / "model"
    assert seen["model_size"] == "small"
    assert seen["device"] == "cpu"
    assert seen["compute_type"] == "int8"
    assert seen["vad_filter"] is False
    assert result.to_dict()["transcript_source"] == "faster-whisper"


def test_portable_pipeline_auto_falls_back_to_whisper_cpp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.application import portable
    from videoflow.domain.state import Sentence

    monkeypatch.delenv("VIDEOWFLOW_ASR_BASE_URL", raising=False)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    seen: dict[str, object] = {}

    class Local:
        def __init__(self, **kwargs: object) -> None:
            seen.update(kwargs)

        def transcribe(self, wav_path: Path, sample_rate: int) -> list[Sentence]:
            return [Sentence(id=0, start_sample=0, end_sample=48000, text="Fallback line")]

    monkeypatch.setattr(
        portable.FasterWhisperAdapter,
        "available",
        staticmethod(lambda *args, **kwargs: False),
    )
    monkeypatch.setattr(portable, "WhisperCliAdapter", Local)
    result = run_portable(
        source,
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcribe=True,
        whisper_model=tmp_path / "model.bin",
        cull_retakes=False,
    )
    assert result.transcript_source == "whisper"
    assert seen["model"] == tmp_path / "model.bin"


def test_portable_pipeline_reuses_project_transcript_and_metadata(
    tmp_path: Path,
) -> None:
    from uuid import uuid4

    from videoflow.domain.config import ModuleEnabled, ModulesConfig
    from videoflow.domain.state import Sentence, WordTiming

    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    project_id = uuid4()
    sentence = Sentence(
        id=7,
        start_sample=0,
        end_sample=48000,
        text="Project transcript.",
        words=[
            WordTiming(
                word="Project",
                start_sample=0,
                end_sample=16000,
                probability=0.9,
            ),
            WordTiming(
                word="transcript.",
                start_sample=16000,
                end_sample=48000,
                probability=0.95,
            ),
        ],
    )
    modules_config = ModulesConfig(
        zooms=ZoomsConfig(mode="alternate_cuts"),
    )
    module_enabled = ModuleEnabled(transcribe=False, shorts=False, retakes=True)
    result = run_portable(
        source,
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcript_sentences=[sentence],
        project_id=project_id,
        revision=9,
        modules_config=modules_config,
        module_enabled=module_enabled,
        cull_retakes=True,
    )
    assert result.transcript_source == "project"
    assert result.state.project_id == project_id
    assert result.state.revision == 9
    assert result.state.modules_config == modules_config
    assert result.state.module_enabled == module_enabled
    assert result.state.transcript[0].words[1].word == "transcript."
    assert result.state.transcript[0].words[1].end_sample == 48000
    assert result.state_path.is_file()
    payload = result.to_dict()
    assert payload["project_id"] == str(project_id)
    assert payload["state_revision"] == 9
    assert payload["transcript_source"] == "project"


def test_portable_pipeline_can_render_shorts(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = tmp_path / "subs.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nFirst.\n\n2\n00:00:02,000 --> 00:00:03,000\nSecond.\n",
        encoding="utf-8",
    )
    result = run_portable(
        source,
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcript_path=transcript,
        shorts=True,
        shorts_count=2,
        shorts_min_sec=1,
        shorts_max_sec=3,
        shorts_subtitles=True,
    )
    assert len(result.shorts) == 1
    assert Path(str(result.shorts[0]["path"])).is_file()
    assert "First." in result.to_dict()["shorts"][0]["title"]


def test_portable_pipeline_fails_when_no_speech_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    with pytest.raises(IngestError, match="No speech"):
        run_portable(
            source,
            tmp_path / "project",
            adapter=FakeAdapter(speech=[]),  # type: ignore[arg-type]
            vad_engine="ffmpeg",
        )


def test_portable_pipeline_runs_silero_at_16k_and_rescales(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from videoflow.application import vad

    class FakeSilero:
        @staticmethod
        def available() -> bool:
            return True

        def __init__(self, **kwargs: object) -> None:
            pass

        def detect(self, wav_path: Path) -> list[tuple[int, int]]:
            assert wav_path.name == "vad.wav"
            return [(0, 16000), (32000, 48000)]

    class RecordingAdapter(FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.rates: list[int] = []

        def extract_pcm(self, source: Path, destination: Path, *, sample_rate: int = 16000) -> Path:
            self.rates.append(sample_rate)
            return super().extract_pcm(source, destination, sample_rate=sample_rate)

    monkeypatch.setattr(vad, "SileroVadAdapter", FakeSilero)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    adapter = RecordingAdapter()
    result = run_portable(
        source,
        tmp_path / "project",
        adapter=adapter,  # type: ignore[arg-type]
        vad_engine="silero",
        speech_pad_before_ms=0,
        speech_pad_after_ms=0,
    )
    assert adapter.rates == [48000, 16000]
    assert result.vad_engine == "silero"
    assert [(item.start_sample, item.end_sample) for item in result.state.vad_intervals] == [
        (0, 48000),
        (96000, 144000),
    ]
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["vad_engine"] == "silero"


def test_speech_pads_are_applied_after_retake_culling(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = tmp_path / "subs.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nFirst take.\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\nSecond take.\n",
        encoding="utf-8",
    )
    result = run_portable(
        source,
        tmp_path / "project",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcript_path=transcript,
        overrides=[ManualOverride(sentence_id=0, action="discard")],
        speech_pad_before_ms=120,
        speech_pad_after_ms=150,
    )
    assert [(item.start_sample, item.end_sample) for item in result.state.vad_intervals] == [
        (90240, 144000)
    ]
    assert len(result.state.video_segments) == 1
