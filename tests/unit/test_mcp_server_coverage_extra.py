"""Extra MCP server coverage through the real registration layer.

Every tool is invoked with ``MCPServer.call_tool`` so request validation,
annotations, and handler dispatch behave exactly as in production. External
boundaries (job manager, ffmpeg, network calls, model adapters) are faked.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from videoflow.adapters.ffmpeg import FFmpegAdapter
from videoflow.domain.errors import (
    BatchError,
    IngestError,
    JobNotFoundError,
    LlmError,
    StateNotReadyError,
    VideoFlowError,
)
from videoflow.domain.state import (
    AudioSegment,
    MediaInfo,
    ProjectState,
    Sentence,
    VideoSegment,
)
from videoflow.mcp_server import server as server_module
from videoflow.mcp_server.server import build_server

ROOTS_ENV = "VIDEOWFLOW_ALLOWED_ROOTS"


def call(server: Any, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        result = await server.call_tool(name, arguments or {})
        return result.structured_content  # type: ignore[attr-defined]

    return asyncio.run(run())


def read(server: Any, uri: str) -> str:
    async def run() -> str:
        contents = await server.read_resource(uri)
        return next(iter(contents)).content  # type: ignore[attr-defined]

    return asyncio.run(run())


def prompt(server: Any, name: str, arguments: dict[str, Any]) -> str:
    async def run() -> str:
        result = await server.get_prompt(name, arguments)
        return str(result.messages[0].content.text)  # type: ignore[attr-defined]

    return asyncio.run(run())


def media(path: Path) -> MediaInfo:
    return MediaInfo(
        source_path=str(path),
        duration_frames=90,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )


def sentence(index: int, text: str = "A sentence.") -> Sentence:
    return Sentence(
        id=index,
        start_sample=index * 96000,
        end_sample=(index + 1) * 96000,
        text=text,
        speaker=0,
    )


class FakeJob:
    def __init__(
        self,
        source: Path,
        output: Path,
        *,
        job_id: str = "job-1",
        status: str = "succeeded",
        result: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.job_id = job_id
        self.source = Path(source)
        self.output = Path(output)
        self.status = status
        self.result = result
        self.options = options or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "source": str(self.source),
            "output": str(self.output),
            "options": self.options,
            "result": self.result,
        }


class FakeManager:
    def __init__(self, job: FakeJob | None = None) -> None:
        self.job = job
        self.started: list[FakeJob] = []

    def _require(self, job_id: str) -> FakeJob:
        if self.job is None or str(job_id) != str(self.job.job_id):
            raise JobNotFoundError(f"Unknown job: {job_id}")
        return self.job

    def get(self, job_id: str) -> FakeJob:
        return self._require(job_id)

    def start(self, source: Path, output: Path, options: Any = None, **kwargs: Any) -> FakeJob:
        result = None
        if (Path(output) / "project_state.json").is_file():
            result = {"state_path": str(Path(output) / "project_state.json")}
        self.job = FakeJob(source, output, result=result, options=dict(options or {}))
        self.started.append(self.job)
        return self.job

    def list(self, *, limit: int | None = None, offset: int = 0) -> list[FakeJob]:
        return [self.job] if self.job is not None else []

    def cancel(self, job_id: str) -> FakeJob:
        return self._require(job_id)

    def pause(self, job_id: str) -> FakeJob:
        return self._require(job_id)

    def unpause(self, job_id: str) -> FakeJob:
        return self._require(job_id)

    def set_priority(self, job_id: str, priority: int) -> FakeJob:
        self._require(job_id).options["priority"] = priority
        return self.job  # type: ignore[return-value]


class FakeBatch:
    def to_dict(self) -> dict[str, Any]:
        return {"batch_id": "batch-1", "status": "queued"}


class FakeBatches:
    def start(self, *args: Any, **kwargs: Any) -> FakeBatch:
        if not Path(args[0]).is_dir():
            raise BatchError(f"Batch source is not a directory: {args[0]}")
        return FakeBatch()

    def get(self, batch_id: str) -> FakeBatch:
        if batch_id != "batch-1":
            raise BatchError(f"Unknown batch: {batch_id}")
        return FakeBatch()

    def cancel(self, batch_id: str) -> FakeBatch:
        return self.get(batch_id)


class Harness:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv(ROOTS_ENV, str(tmp_path))
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.tmp = tmp_path
        self.source = tmp_path / "source.mp4"
        self.source.write_bytes(b"x")
        self.output = tmp_path / "out"
        self.output.mkdir()
        self.manager = FakeManager()
        self.server = build_server(self.manager, FakeBatches())

    def load(self) -> None:
        payload = call(self.server, "videoflow_load_media", {"file_path": str(self.source)})
        assert payload["ok"] is True, payload

    def write_state(
        self,
        *,
        transcript: list[Sentence] | None = None,
        with_media: bool = True,
        raw: str | None = None,
    ) -> Path:
        path = self.output / "project_state.json"
        if raw is not None:
            path.write_text(raw, encoding="utf-8")
            return path
        state = ProjectState(
            media_info=media(self.source) if with_media else None,
            transcript=transcript or [],
        )
        path.write_text(state.model_dump_json(), encoding="utf-8")
        return path

    def attach_job(
        self,
        *,
        status: str = "succeeded",
        result: dict[str, Any] | None = None,
    ) -> FakeJob:
        job = FakeJob(self.source, self.output, status=status, result=result)
        self.manager.job = job
        return job

    def pipeline(self, **overrides: Any) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "source": str(self.source),
            "output": str(self.output),
        }
        arguments.update(overrides)
        payload = call(self.server, "videoflow_run_pipeline", arguments)
        assert payload["ok"] is True, payload
        return payload


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Harness:
    monkeypatch.setattr(FFmpegAdapter, "probe", lambda self, path: media(Path(path)))
    return Harness(monkeypatch, tmp_path)


def test_asset_upload_import_and_config_errors(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server
    outside = "/etc/passwd"

    assert call(server, "videoflow_upload_music", {"file_path": outside})["code"] == (
        "path_not_allowed"
    )
    assert call(server, "videoflow_upload_image", {"file_path": outside})["code"] == (
        "path_not_allowed"
    )
    assert call(server, "videoflow_upload_font", {"file_path": outside})["code"] == (
        "path_not_allowed"
    )

    imported: list[Path] = []

    def fake_import(*args: Any, **kwargs: Any) -> Path:
        imported.append(harness.source)
        return harness.source

    monkeypatch.setattr(server_module, "import_url", fake_import)
    payload = call(server, "videoflow_import_url", {"url": "https://example.invalid/v"})
    assert payload["ok"] is True
    assert payload["path"] == str(harness.source)
    assert payload["media"]["duration_frames"] == 90
    assert imported

    monkeypatch.setattr(server_module, "import_url", lambda *a, **k: harness.source)
    monkeypatch.setattr(
        FFmpegAdapter, "probe", lambda self, path: (_ for _ in ()).throw(IngestError("bad"))
    )
    assert call(server, "videoflow_import_url", {"url": "https://example.invalid/v"})["code"] == (
        "ingest_failed"
    )
    monkeypatch.setattr(FFmpegAdapter, "probe", lambda self, path: media(Path(path)))

    bad_template = call(
        server,
        "videoflow_save_project_template",
        {"name": "bad", "template": {"description": 3}},
    )
    assert bad_template["ok"] is False
    assert bad_template["code"] == "invalid_template"
    assert call(
        server, "videoflow_import_config", {"schema_version": 2, "options": {}}
    )["code"] == ("invalid_config")
    assert call(
        server,
        "videoflow_save_brand_template",
        {"name": "bad", "template": {"caption_style": "nope"}},
    )["code"] == ("invalid_template")

    assert call(server, "videoflow_export_config", {"options": {"crf": 18}})["ok"] is True

    missing_source = call(
        server,
        "videoflow_save_schedule",
        {"schedule": {"id": "s1", "recipe_id": "youtube_talking_head"}},
    )
    assert missing_source["ok"] is False
    invalid_schedule = call(
        server, "videoflow_save_schedule", {"schedule": {"id": "s1", "interval_seconds": 1}}
    )
    assert invalid_schedule["ok"] is False

    assert call(server, "videoflow_get_recipe", {"recipe_id": "missing"})["code"] == (
        "recipe_invalid"
    )
    assert call(
        server,
        "videoflow_validate_recipe",
        {"recipe": {"schema_version": 1, "id": "x", "name": "x", "steps": []}},
    )["code"] == ("recipe_invalid")
    assert call(
        server,
        "videoflow_save_recipe",
        {"recipe": {"schema_version": 1, "id": "x", "name": "x", "steps": []}},
    )["code"] == ("recipe_invalid")
    assert call(server, "videoflow_list_plugins", {"limit": 0, "offset": 0})["ok"] is True
    assert call(server, "videoflow_list_models", {"limit": 0})["ok"] is True
    assert call(server, "videoflow_list_steps", {"limit": 0})["ok"] is True
    assert call(server, "videoflow_list_recipes", {"limit": 0})["ok"] is True


def test_media_vad_and_transcribe_paths(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server
    harness.load()
    # A second load of the same source keeps the pending state (branch 548->561).
    harness.load()

    for arguments, code in [
        ({"noise_db": -1.0}, "invalid_arguments"),
        ({"min_silence_ms": -1}, "invalid_arguments"),
        ({"min_speech_ms": -1}, "invalid_arguments"),
        ({"vad_engine": "nope"}, "invalid_arguments"),
        ({"speech_threshold": 0.0}, "invalid_arguments"),
        ({"speech_pad_before_ms": -1}, "invalid_arguments"),
        ({"speech_pad_after_ms": -1}, "invalid_arguments"),
    ]:
        assert call(server, "videoflow_run_vad", arguments)["code"] == code

    monkeypatch.setattr(
        server_module, "detect_vad", lambda *a, **k: (_ for _ in ()).throw(IngestError("no"))
    )
    assert call(server, "videoflow_run_vad", {})["code"] == "ingest_failed"

    for arguments in [
        {"language": "zz"},
        {"engine": "nope"},
        {"device": "tpu"},
        {"compute_type": "bf16"},
    ]:
        assert call(server, "videoflow_transcribe", arguments)["code"] == "invalid_arguments"

    class FakeFasterWhisper:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def transcribe(self, wav: Path, rate: int) -> list[Sentence]:
            return [sentence(0, "Faster.")]

    class FakeWhisper:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def transcribe(self, wav: Path, rate: int) -> list[Sentence]:
            return [sentence(0, "Plain.")]

    monkeypatch.setattr(FFmpegAdapter, "extract_pcm", lambda self, *a, **k: harness.source)
    monkeypatch.setattr(server_module, "FasterWhisperAdapter", FakeFasterWhisper)
    monkeypatch.setattr(server_module, "WhisperCliAdapter", FakeWhisper)
    monkeypatch.setattr(server_module, "find_faster_whisper_model", lambda model: None)
    monkeypatch.setattr(
        server_module, "expected_faster_whisper_model", lambda model: Path("/models") / model
    )

    faster = call(
        server,
        "videoflow_transcribe",
        {"engine": "faster-whisper", "language": "en"},
    )
    assert faster["ok"] is True
    assert faster["source"] == "faster-whisper"
    assert faster["model"].endswith("small")
    assert faster["transcript"][0]["text"] == "Faster."
    assert (harness.tmp / "source-videoflow" / "work" / "mcp-transcript.srt").is_file()

    model_file = harness.tmp / "ggml-small.bin"
    model_file.write_bytes(b"model")
    plain = call(
        server,
        "videoflow_transcribe",
        {"engine": "whisper.cpp", "model": str(model_file)},
    )
    assert plain["ok"] is True
    assert plain["source"] == "whisper"
    assert plain["model"] == str(model_file)

    monkeypatch.setattr(
        server_module, "format_srt", lambda *a, **k: (_ for _ in ()).throw(OSError("disk"))
    )
    broken = call(server, "videoflow_transcribe", {"engine": "whisper.cpp"})
    assert broken["code"] == "transcript_write_failed"

    monkeypatch.setattr(
        server_module,
        "FasterWhisperAdapter",
        type(
            "Boom",
            (),
            {
                "__init__": lambda self, **k: None,
                "transcribe": lambda self, *a, **k: (_ for _ in ()).throw(
                    IngestError("asr failed")
                ),
            },
        ),
    )
    failed = call(server, "videoflow_transcribe", {"engine": "faster-whisper"})
    assert failed["code"] == "ingest_failed"


def test_transcript_retake_and_zoom_validation(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server

    assert call(server, "videoflow_get_transcript", {})["code"] == "transcript_not_found"
    assert call(server, "videoflow_cull_retakes", {})["code"] == "transcript_not_found"
    assert call(
        server, "videoflow_cull_retakes", {"manual_word_indices": [0]}
    )["code"] == ("word_overrides_not_supported")

    for arguments in [
        {"mode": "nope"},
        {"scale": 1.0},
        {"anchor": "corner"},
    ]:
        assert call(server, "videoflow_configure_zooms", arguments)["code"] == (
            "invalid_arguments"
        )
    for arguments in [{"offset_ms": 0}, {"crossfade_ms": 0}]:
        assert call(server, "videoflow_apply_jcuts", arguments)["code"] == "invalid_arguments"

    harness.load()
    harness.write_state(transcript=[sentence(0), sentence(1)])
    harness.pipeline()
    unknown = call(server, "videoflow_cull_retakes", {"discard_sentence_ids": [99]})
    assert unknown["code"] == "invalid_retake_ids"
    assert unknown["unknown_ids"] == [99]
    culled = call(server, "videoflow_cull_retakes", {"discard_sentence_ids": [0]})
    assert culled["ok"] is True

    transcript = call(server, "videoflow_get_transcript", {})
    assert transcript["ok"] is True
    assert transcript["sentence_count"] == 2

    harness.write_state(raw="{not json")
    assert call(server, "videoflow_get_transcript", {})["code"] == "transcript_not_found"


def test_short_tool_validation_and_job_states(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server

    assert call(server, "videoflow_edit_short", {"index": -1})["code"] == "invalid_arguments"
    assert call(
        server, "videoflow_edit_short", {"index": 0, "aspect_ratio": "4:3"}
    )["code"] == ("invalid_arguments")
    assert call(
        server, "videoflow_edit_short", {"index": 0, "start_sec": 2, "end_sec": 1}
    )["code"] == ("invalid_arguments")

    for name in [
        "videoflow_edit_short",
        "videoflow_generate_short_emoji",
        "videoflow_generate_short_metadata",
        "videoflow_generate_short_thumbnail",
        "videoflow_generate_short_voiceover",
        "videoflow_dub_short",
        "videoflow_analyze_short",
        "videoflow_analyze_short_llm",
        "videoflow_schedule_short",
    ]:
        arguments: dict[str, Any] = {}
        if name == "videoflow_generate_short_voiceover":
            arguments = {"index": 0, "text": "hello"}
        elif name == "videoflow_dub_short":
            arguments = {"index": 0}
        elif name == "videoflow_schedule_short":
            arguments = {"index": 0, "target": "demo"}
        else:
            arguments = {"index": 0}
        payload = call(server, name, arguments)
        assert payload["code"] == "job_required", name

    assert call(
        server, "videoflow_generate_short_metadata", {"index": 0, "platform": "myspace"}
    )["code"] == ("invalid_arguments")
    assert call(
        server, "videoflow_generate_short_metadata", {"index": 0, "tone": "sassy"}
    )["code"] == ("invalid_arguments")

    assert call(
        server, "videoflow_generate_shorts", {"min_duration": 1, "max_duration": 10}
    )["code"] == ("transcript_not_found")

    harness.load()
    harness.write_state(transcript=[sentence(0), sentence(1)])
    harness.pipeline()
    job = harness.attach_job(status="queued", result=None)
    short_calls = {
        "videoflow_edit_short": {"index": 0},
        "videoflow_generate_short_emoji": {"index": 0},
        "videoflow_generate_short_metadata": {"index": 0},
        "videoflow_generate_short_thumbnail": {"index": 0},
        "videoflow_generate_short_voiceover": {"index": 0, "text": "hello"},
        "videoflow_dub_short": {"index": 0},
        "videoflow_analyze_short": {"index": 0},
        "videoflow_analyze_short_llm": {"index": 0},
        "videoflow_schedule_short": {"index": 0, "target": "demo"},
    }
    for name, arguments in short_calls.items():
        assert call(server, name, arguments)["code"] == "state_not_ready", name

    job.status = "succeeded"
    job.result = {"shorts": []}
    assert call(
        server, "videoflow_schedule_short", {"index": 0, "target": "demo"}
    )["code"] == "state_not_ready"
    job.result = {"shorts": [{}]}
    assert call(
        server, "videoflow_schedule_short", {"index": 0, "target": "demo"}
    )["code"] == "state_not_ready"

    short = {"title": "Hook", "path": str(harness.tmp / "short.mp4"), "score": 80}
    job.result = {"shorts": [short], "state_path": str(harness.output / "project_state.json")}

    monkeypatch.setattr(
        server_module, "edit_short_service", lambda **kwargs: {"title": "Edited"}
    )
    assert call(server, "videoflow_edit_short", {"index": 0, "title": "Edited"})["ok"] is True

    monkeypatch.setattr(
        server_module,
        "apply_llm_emoji",
        lambda **kwargs: {"emoji_map": {"a": "b"}, "short": {"title": "Hook"}},
    )
    assert call(server, "videoflow_generate_short_emoji", {"index": 0})["ok"] is True

    from videoflow.application import short_metadata as metadata_module

    metadata_stub = lambda **kwargs: {  # noqa: E731
        "title": "T",
        "description": "D",
        "hashtags": ["#t"],
    }
    monkeypatch.setattr(metadata_module, "generate_short_metadata", metadata_stub)
    monkeypatch.setattr(server_module, "generate_short_metadata", metadata_stub)
    assert call(server, "videoflow_generate_short_metadata", {"index": 0})["ok"] is True, call(
        server, "videoflow_generate_short_metadata", {"index": 0}
    )

    monkeypatch.setattr(
        server_module, "generate_short_thumbnail", lambda **kwargs: {"path": "thumb.png"}
    )
    assert call(server, "videoflow_generate_short_thumbnail", {"index": 0})["ok"] is True

    monkeypatch.setattr(
        server_module, "generate_short_voiceover", lambda **kwargs: {"path": "voice.mp3"}
    )
    assert call(
        server, "videoflow_generate_short_voiceover", {"index": 0, "text": "hello"}
    )["ok"] is True

    monkeypatch.setattr(
        server_module, "generate_short_dubbing", lambda **kwargs: {"path": "dub.mp3"}
    )
    assert call(server, "videoflow_dub_short", {"index": 0})["ok"] is True

    monkeypatch.setattr(server_module, "analyze_short_entry", lambda **kwargs: {"score": 1})
    assert call(server, "videoflow_analyze_short", {"index": 0})["ok"] is True

    monkeypatch.setattr(
        server_module, "analyze_short_llm_entry", lambda **kwargs: {"score": 2}
    )
    monkeypatch.delenv("VIDEOWFLOW_VISION_BASE_URL", raising=False)
    assert call(server, "videoflow_analyze_short_llm", {"index": 0})["code"] == ("not_implemented")
    assert call(
        server,
        "videoflow_analyze_short_llm",
        {"index": 0, "base_url": "http://127.0.0.1:9/v1"},
    )["ok"] is True


def test_schedule_short_metadata_and_publish_errors(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server
    harness.load()
    harness.write_state(transcript=[sentence(0)])
    harness.pipeline()
    job = harness.attach_job(
        result={"shorts": [{"title": "Hook", "path": str(harness.tmp / "s.mp4")}]}
    )

    from videoflow.application import short_metadata as metadata_module

    metadata_stub = lambda **kwargs: {  # noqa: E731
        "title": "T",
        "description": "D",
        "hashtags": ["#a"],
    }
    monkeypatch.setattr(metadata_module, "generate_short_metadata", metadata_stub)
    monkeypatch.setattr(server_module, "generate_short_metadata", metadata_stub)
    monkeypatch.setattr(
        server_module,
        "enqueue_publish",
        lambda **kwargs: {"id": "item-1"},
    )
    assert call(server, "videoflow_schedule_short", {"index": 0, "target": "demo"})["ok"] is True
    monkeypatch.setattr(
        server_module,
        "enqueue_publish",
        lambda **kwargs: (_ for _ in ()).throw(StateNotReadyError("no target")),
    )
    failed = call(server, "videoflow_schedule_short", {"index": 0, "target": "demo"})
    assert failed["code"] == "state_not_ready"

    job.status = "failed"
    job.result = None
    assert call(server, "videoflow_schedule_short", {"index": 0, "target": "demo"})["code"] == (
        "state_not_ready"
    )

    assert call(server, "videoflow_edit_short", {"index": 0})["code"] == "state_not_ready"
    assert call(server, "videoflow_generate_short_emoji", {"index": 0})["code"] == (
        "state_not_ready"
    )
    assert call(server, "videoflow_generate_short_metadata", {"index": 0})["code"] == (
        "state_not_ready"
    )
    assert call(server, "videoflow_generate_short_thumbnail", {"index": 0})["code"] == (
        "state_not_ready"
    )
    assert call(
        server, "videoflow_generate_short_voiceover", {"index": 0, "text": "x"}
    )["code"] == ("state_not_ready")
    assert call(server, "videoflow_dub_short", {"index": 0})["code"] == "state_not_ready"
    assert call(server, "videoflow_analyze_short", {"index": 0})["code"] == "state_not_ready"
    assert call(server, "videoflow_analyze_short_llm", {"index": 0})["code"] == (
        "state_not_ready"
    )


def test_generate_shorts_boost_and_llm_paths(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server
    harness.load()
    harness.write_state(transcript=[sentence(0), sentence(1), sentence(2)])
    harness.pipeline()

    from videoflow.application import audio_analysis, video_analysis

    monkeypatch.setattr(video_analysis, "detect_scene_changes", lambda source: [(0.0, 1.0)])
    monkeypatch.setattr(video_analysis, "scene_intervals", lambda cuts, sample_rate: [(0, 48000)])
    boosted = call(
        server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 10, "count": 1, "scene_change_boost": True},
    )
    assert boosted["ok"] is True
    assert boosted["scene_change_boost"] is True

    monkeypatch.setattr(
        video_analysis,
        "detect_scene_changes",
        lambda source: (_ for _ in ()).throw(VideoFlowError("scene failed")),
    )
    tolerated = call(
        server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 10, "count": 1, "scene_change_boost": True},
    )
    assert tolerated["ok"] is True

    monkeypatch.setattr(audio_analysis, "detect_audio_energy", lambda source, rate: [(0, 48000)])
    energy = call(
        server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 10, "count": 1, "audio_energy_boost": True},
    )
    assert energy["ok"] is True
    assert energy["audio_energy_boost"] is True

    monkeypatch.setattr(audio_analysis, "detect_audio_energy", lambda source, rate: [])
    no_energy = call(
        server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 10, "count": 1, "audio_energy_boost": True},
    )
    assert no_energy["ok"] is True

    monkeypatch.setattr(
        audio_analysis,
        "detect_audio_energy",
        lambda source, rate: (_ for _ in ()).throw(VideoFlowError("energy failed")),
    )
    tolerated = call(
        server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 10, "count": 1, "audio_energy_boost": True},
    )
    assert tolerated["ok"] is True

    monkeypatch.setenv("VIDEOWFLOW_LLM_BASE_URL", "http://example.invalid/v1")
    blocked = call(
        server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 10, "count": 1, "selection_mode": "heuristic"},
    )
    assert blocked["code"] == "not_implemented"
    monkeypatch.setattr(server_module, "OpenAICompatibleLlm", lambda **kwargs: object())
    allowed = call(
        server,
        "videoflow_generate_shorts",
        {
            "min_duration": 1,
            "max_duration": 10,
            "count": 1,
            "selection_mode": "heuristic",
            "allow_external_services": True,
            "allowed_external_hosts": ["example.invalid"],
        },
    )
    assert allowed["ok"] is True

    monkeypatch.delenv("VIDEOWFLOW_LLM_BASE_URL")
    (harness.tmp / "media-less").mkdir(exist_ok=True)
    media_less = Harness(monkeypatch, harness.tmp / "media-less")
    media_less.write_state(transcript=[sentence(0)], with_media=False)
    media_less.pipeline()
    before_load = call(
        media_less.server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 10},
    )
    assert before_load["code"] == "media_not_found"
    media_less.load()
    missing_media = call(
        media_less.server,
        "videoflow_generate_shorts",
        {"min_duration": 1, "max_duration": 10},
    )
    assert missing_media["code"] == "media_not_found"


def test_timeline_jobs_and_copilot(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server

    assert call(server, "videoflow_get_timeline", {})["code"] == "state_not_ready"
    for name, arguments in [
        ("videoflow_pause_job", {"job_id": "missing"}),
        ("videoflow_unpause_job", {"job_id": "missing"}),
        ("videoflow_set_job_priority", {"job_id": "missing", "priority": 2}),
        ("videoflow_cancel_job", {"job_id": "missing"}),
        ("videoflow_get_job", {"job_id": "missing"}),
    ]:
        assert call(server, name, arguments)["code"] == "job_not_found", name

    assert call(server, "videoflow_list_clip_comments", {"job_id": "missing"})["code"] == (
        "job_not_found"
    )
    assert call(
        server, "videoflow_add_clip_comment", {"clip_id": "v1", "text": "t", "job_id": "missing"}
    )["code"] == ("job_not_found")
    assert call(server, "videoflow_remove_clip_comment", {"comment_id": "c", "job_id": "missing"})[
        "code"
    ] == ("job_not_found")
    assert call(server, "videoflow_validate_exports", {"job_id": "missing"})["code"] == (
        "job_not_found"
    )
    assert call(server, "videoflow_edit_timeline", {"clip_id": "v1", "action": "move"})[
        "code"
    ] == ("state_not_ready")
    assert call(server, "videoflow_approve_broll", {"title": "t", "approved": []})["code"] == (
        "state_not_ready"
    )
    assert call(server, "videoflow_decide_review", {"approved": True})["code"] == (
        "state_not_ready"
    )
    assert call(server, "videoflow_copilot_timeline", {"prompt": "x"})["code"] == (
        "state_not_ready"
    )
    assert call(server, "videoflow_render_frame", {"time_sec": 1.0})["code"] == (
        "state_not_ready"
    )

    harness.load()
    harness.pipeline()
    harness.write_state(raw="{bad state")
    assert call(server, "videoflow_get_timeline", {})["code"] == "state_not_ready"
    assert call(server, "videoflow_render_frame", {"time_sec": 1.0})["code"] == (
        "state_not_ready"
    )
    assert call(server, "videoflow_copilot_timeline", {"prompt": "x"})["code"] == (
        "state_not_ready"
    )

    (harness.output / "project_state.json").unlink()
    assert call(server, "videoflow_get_timeline", {})["code"] == "state_not_ready"

    harness.write_state(transcript=[sentence(0)])
    harness.manager.job.result = timeline_state(harness)
    state = ProjectState.model_validate_json(
        (harness.output / "project_state.json").read_text(encoding="utf-8")
    )
    assert state.transcript

    real_apply = server_module.apply_timeline_edit
    monkeypatch.setattr(
        server_module,
        "apply_timeline_edit",
        lambda *a, **k: (_ for _ in ()).throw(StateNotReadyError("bad edit")),
    )
    assert call(server, "videoflow_edit_timeline", {"clip_id": "v1", "action": "move"})["code"] == (
        "state_not_ready"
    )

    from videoflow.application import broll_approval, deliverables

    monkeypatch.setattr(
        broll_approval,
        "save_approval",
        lambda *a, **k: (_ for _ in ()).throw(StateNotReadyError("broll")),
    )
    assert call(server, "videoflow_approve_broll", {"title": "t", "approved": [0]})["code"] == (
        "state_not_ready"
    )
    monkeypatch.setattr(
        deliverables,
        "approve_review",
        lambda *a, **k: (_ for _ in ()).throw(StateNotReadyError("review")),
    )
    assert call(server, "videoflow_decide_review", {"approved": True})["code"] == (
        "state_not_ready"
    )

    assert call(
        server,
        "videoflow_add_timeline_overlay",
        {"path": "/etc/passwd", "start_sec": 0.0, "duration_sec": 1.0},
    )["code"] == ("path_not_allowed")
    monkeypatch.setattr(
        server_module,
        "resolve_allowed",
        lambda *a, **k: (_ for _ in ()).throw(OSError("denied")),
    )
    assert call(
        server,
        "videoflow_add_timeline_overlay",
        {"path": str(harness.source), "start_sec": 0.0, "duration_sec": 1.0},
    )["code"] == ("overlay_failed")

    assert call(
        server, "videoflow_remove_timeline_overlay", {"overlay_id": "missing"}
    )["code"] == ("state_not_ready")

    monkeypatch.setattr(server_module, "build_llm", lambda: object())
    monkeypatch.setattr(
        server_module, "propose_recipe", lambda *a, **k: (_ for _ in ()).throw(LlmError("no"))
    )
    assert call(server, "videoflow_copilot_recipe", {"prompt": "x"})["code"] == "llm_failed"

    from videoflow.core.recipe import parse_recipe

    drafted = parse_recipe(
        {
            "schema_version": 1,
            "id": "copilot_extra",
            "name": "Copilot",
            "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
        }
    )
    monkeypatch.setattr(server_module, "propose_recipe", lambda client, prompt: drafted)
    assert call(server, "videoflow_copilot_recipe", {"prompt": "x"})["recipe"]["id"] == (
        "copilot_extra"
    )

    monkeypatch.setattr(server_module, "propose_timeline_edits", lambda *a, **k: [])
    proposed = call(server, "videoflow_copilot_timeline", {"prompt": "x", "apply": False})
    assert proposed["ok"] is True
    assert proposed["applied"] is False

    monkeypatch.setattr(server_module, "apply_timeline_edit", real_apply)
    monkeypatch.setattr(
        server_module,
        "propose_timeline_edits",
        lambda *a, **k: [
            {"clip_id": "v1", "action": "trim", "start_sec": 0.0, "end_sec": 0.5}
        ],
    )
    applied = call(server, "videoflow_copilot_timeline", {"prompt": "trim", "apply": True})
    assert applied["ok"] is True
    assert applied["applied"] is True

    monkeypatch.setattr(
        server_module,
        "propose_timeline_edits",
        lambda *a, **k: (_ for _ in ()).throw(LlmError("no edits")),
    )
    assert call(server, "videoflow_copilot_timeline", {"prompt": "x", "apply": True})["code"] == (
        "llm_failed"
    )

    missing_source = harness.tmp / "gone.mp4"
    state = ProjectState(media_info=media(missing_source), transcript=[sentence(0)])
    (harness.output / "project_state.json").write_text(
        state.model_dump_json(), encoding="utf-8"
    )
    assert call(server, "videoflow_render_frame", {"time_sec": 1.0})["code"] == (
        "state_not_ready"
    )

    harness.source.write_bytes(b"x")
    state = ProjectState(media_info=media(harness.source), transcript=[sentence(0)])
    state_path = harness.output / "project_state.json"
    state_path.write_text(state.model_dump_json(), encoding="utf-8")
    harness.manager.job.result = {"state_path": str(state_path), "shorts": []}
    monkeypatch.setattr(
        FFmpegAdapter,
        "render_thumbnail",
        lambda self, source, target, time_sec=0.0: Path(target).write_bytes(b"jpg"),
    )
    rendered = call(server, "videoflow_render_frame", {"time_sec": 1.25})
    assert rendered["ok"] is True
    assert rendered["path"].endswith("00000012.jpg")
    assert call(server, "videoflow_list_jobs", {"limit": 5})["ok"] is True


def test_pipeline_recipe_batch_and_schedule_paths(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server

    assert call(server, "videoflow_run_pipeline", {})["code"] == "source_required"
    assert call(server, "videoflow_run_recipe", {"recipe_id": "youtube_talking_head"})[
        "code"
    ] == ("source_required")
    assert call(
        server,
        "videoflow_run_recipe_inline",
        {"recipe": {"schema_version": 1, "id": "x", "name": "x", "steps": []}},
    )["code"] == ("source_required")
    assert call(server, "videoflow_run_step", {"step_id": "ingest"})["code"] == (
        "recipe_required"
    )
    assert call(
        server,
        "videoflow_run_step",
        {
            "step_id": "ingest",
            "recipe": {"schema_version": 1, "id": "x", "name": "x", "steps": []},
            "recipe_id": "x",
        },
    )["code"] == ("recipe_required")
    assert call(server, "videoflow_run_batch", {})["code"] == "recipe_required"
    assert call(server, "videoflow_get_batch", {"batch_id": "missing"})["code"] == (
        "batch_invalid"
    )
    assert call(server, "videoflow_cancel_batch", {"batch_id": "missing"})["code"] == (
        "batch_invalid"
    )

    recipe = {
        "schema_version": 1,
        "id": "mcp_extra",
        "name": "MCP extra",
        "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
    }
    assert call(
        server,
        "videoflow_run_recipe_inline",
        {"recipe": recipe, "source": str(harness.source), "output": str(harness.tmp / "o1")},
    )["ok"] is True
    assert call(
        server,
        "videoflow_run_step",
        {
            "step_id": "nope",
            "recipe": recipe,
            "source": str(harness.source),
            "output": str(harness.tmp / "o2"),
        },
    )["code"] == ("unknown_step")
    assert call(
        server,
        "videoflow_run_recipe",
        {"recipe_id": "missing", "source": str(harness.source)},
    )["code"] == ("recipe_invalid")
    assert call(
        server,
        "videoflow_run_batch",
        {
            "recipe": recipe,
            "source_dir": str(harness.tmp / "missing"),
            "output_root": str(harness.tmp / "bo"),
        },
    )["code"] == ("batch_invalid")

    assert call(
        server,
        "videoflow_run_pipeline",
        {"source": str(harness.source), "overrides": {"bogus": 1}},
    )["code"] == ("invalid_overrides")
    assert call(
        server,
        "videoflow_run_pipeline",
        {"source": str(harness.source), "overrides": {"transcript": "/etc/passwd"}},
    )["code"] == ("path_not_allowed")

    project_template = call(
        server,
        "videoflow_save_project_template",
        {"name": "demo", "template": {"description": "d", "options": {"crf": 18}}},
    )
    assert project_template["ok"] is True
    brand_template = call(
        server,
        "videoflow_save_brand_template",
        {"name": "demo", "template": {"name": "demo"}},
    )
    assert brand_template["ok"] is True

    assert call(server, "videoflow_configure_zooms", {"mode": "manual_rules"})["ok"] is True
    transcript_path = harness.output / "transcript.srt"
    transcript_path.write_text("1\n", encoding="utf-8")
    started = call(
        server,
        "videoflow_run_pipeline",
        {
            "source": str(harness.source),
            "output": str(harness.output),
            "overrides": {
                "zoom_mode": "manual_rules",
                "project_template": "demo",
                "brand_template": "demo",
                "transcript": str(transcript_path),
            },
        },
    )
    assert started["ok"] is True, started
    options = harness.manager.job.options
    assert options["zoom_mode"] == "manual_rules"
    assert options["zooms"] is True
    assert options["crf"] == 18
    assert options["transcript"] == str(transcript_path)
    assert "caption_font_family" in options

    schedule = call(
        server,
        "videoflow_save_schedule",
        {
            "schedule": {
                "id": "sched-1",
                "source": str(harness.source),
                "output": str(harness.tmp / "sched-out"),
                "recipe_id": "youtube_talking_head",
            }
        },
    )
    assert schedule["ok"] is True, schedule
    ran = call(server, "videoflow_run_schedule", {"schedule_id": "sched-1"})
    assert ran["ok"] is True
    assert ran["schedule"]["status"] in {"queued", "retry in 30s"}


def test_export_models_backup_and_resources(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server

    assert call(server, "videoflow_export_fcpxml", {"output_path": str(harness.tmp / "x")})[
        "code"
    ] == ("state_not_found")

    harness.load()
    harness.write_state(transcript=[sentence(0)])
    harness.pipeline()

    monkeypatch.setattr(
        server_module, "export_timeline", lambda *a, **k: (_ for _ in ()).throw(OSError("io"))
    )
    assert call(
        server, "videoflow_export_fcpxml", {"output_path": str(harness.tmp / "x.fcpxml")}
    )["code"] == ("export_failed")

    monkeypatch.setattr(
        server_module,
        "install_model",
        lambda *a, **k: (_ for _ in ()).throw(VideoFlowError("download")),
    )
    assert call(server, "videoflow_install_model", {"model_id": "demo"})["code"] == (
        "videoflow_error"
    )
    monkeypatch.setattr(
        server_module,
        "remove_model",
        lambda *a, **k: (_ for _ in ()).throw(VideoFlowError("missing")),
    )
    assert call(server, "videoflow_remove_model", {"model_id": "demo"})["code"] == (
        "videoflow_error"
    )

    monkeypatch.setattr(
        server_module, "scheduled_backup", lambda: (_ for _ in ()).throw(OSError("disk"))
    )
    assert call(server, "videoflow_create_backup", {})["code"] == "backup_failed"

    assert call(server, "videoflow_set_plugin_enabled", {"plugin_id": "x", "enabled": True})[
        "code"
    ] == "plugin_not_found"

    artifact = harness.tmp / "timeline.fcpxml"
    artifact.write_text("x", encoding="utf-8")
    (harness.output / "run.json").write_text(
        json.dumps({"artifacts": {"resolve": str(artifact)}}), encoding="utf-8"
    )
    assert json.loads(read(server, "videoflow://project/exports"))["ok"] is True
    (harness.output / "run.json").write_text("{bad", encoding="utf-8")
    assert json.loads(read(server, "videoflow://project/exports"))["code"] == (
        "exports_unreadable"
    )

    fresh = Harness(monkeypatch, harness.tmp / "fresh")
    (harness.tmp / "fresh").mkdir(exist_ok=True)
    assert json.loads(read(fresh.server, "videoflow://project/exports"))["code"] == (
        "exports_not_found"
    )
    assert json.loads(read(fresh.server, "videoflow://project/state"))["code"] == (
        "state_not_found"
    )
    assert json.loads(read(fresh.server, "videoflow://project/transcript"))["code"] == (
        "transcript_not_found"
    )

    produce = prompt(
        fresh.server,
        "videoflow_produce",
        {"source": "a.mp4", "output": "out", "recipe_id": "youtube_talking_head"},
    )
    assert "youtube_talking_head" in produce
    review = prompt(fresh.server, "videoflow_review", {"job_id": "j1", "instruction": "trim"})
    assert "j1" in review
    deliver = prompt(fresh.server, "videoflow_deliver", {"job_id": "j2"})
    assert "j2" in deliver

    class FakeItem:
        def __init__(self, name: str) -> None:
            self.name = name

        def read_text(self, encoding: str) -> str:
            return '{"id": "shipped"}'

    class FakeDir:
        def iterdir(self):
            return [FakeItem("readme.txt"), FakeItem("shipped.json")]

    monkeypatch.setattr(server_module, "files", lambda package: type("P", (), {
        "joinpath": lambda self, name: FakeDir(),
    })())
    presets = json.loads(read(fresh.server, "videoflow://presets/list"))
    assert presets["presets"]["shipped.json"]["source"] == "shipped"

    monkeypatch.setattr(
        server_module, "files", lambda package: (_ for _ in ()).throw(OSError("pkg"))
    )
    presets = json.loads(read(fresh.server, "videoflow://presets/list"))
    assert presets["ok"] is True


def test_asset_upload_success_and_small_tools(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server
    music = harness.tmp / "track.mp3"
    music.write_bytes(b"ID3audio")
    image = harness.tmp / "logo.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    font = harness.tmp / "font.ttf"
    font.write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 16)

    assert call(server, "videoflow_upload_music", {"file_path": str(music)})["ok"] is True
    assert call(server, "videoflow_upload_image", {"file_path": str(image)})["ok"] is True
    monkeypatch.setattr(server_module, "save_font", lambda name, data: {"name": name})
    assert call(server, "videoflow_upload_font", {"file_path": str(font)})["ok"] is True
    assert call(server, "videoflow_list_music", {})["music"]
    assert call(server, "videoflow_list_images", {})["images"]
    assert "fonts" in call(server, "videoflow_list_fonts", {})
    assert call(server, "videoflow_list_capabilities", {})["ok"] is True
    assert call(server, "videoflow_list_project_templates", {})["ok"] is True
    assert call(server, "videoflow_list_brand_templates", {})["ok"] is True
    assert call(server, "videoflow_list_publish_targets", {})["ok"] is True
    assert call(server, "videoflow_list_publish_queue", {})["ok"] is True
    assert "providers" in call(server, "videoflow_list_providers", {})
    assert call(server, "videoflow_list_schedules", {})["ok"] is True
    assert call(server, "videoflow_list_models", {})["ok"] is True
    assert call(server, "videoflow_list_plugins", {})["ok"] is True
    assert call(server, "videoflow_cost_metrics", {})["ok"] is True
    assert call(server, "videoflow_reload_plugins", {})["ok"] is True
    assert call(server, "videoflow_import_config", {"schema_version": 1, "options": {}})[
        "ok"
    ] is True

    assert call(
        server,
        "videoflow_save_publish_target",
        {"name": "t", "webhook_url": "http://127.0.0.1:9/hook"},
    )["ok"] is True
    assert call(
        server,
        "videoflow_save_project_template",
        {"name": "---", "template": {}},
    )["code"] == "filesystem_error"
    assert call(
        server,
        "videoflow_save_brand_template",
        {"name": "---", "template": {}},
    )["code"] == "filesystem_error"

    monkeypatch.setattr(server_module, "install_model", lambda model_id, allow_network: {"id": 1})
    monkeypatch.setattr(server_module, "remove_model", lambda model_id: None)
    assert call(server, "videoflow_install_model", {"model_id": "demo"})["ok"] is True
    assert call(server, "videoflow_remove_model", {"model_id": "demo"})["ok"] is True

    monkeypatch.setattr(server_module, "scheduled_backup", lambda: harness.tmp / "db.bak")
    assert call(server, "videoflow_create_backup", {})["ok"] is True

    assert call(server, "videoflow_run_schedule", {"schedule_id": "missing"})["code"] == (
        "state_not_ready"
    )
    assert call(server, "videoflow_load_media", {"file_path": "/etc/passwd"})["code"] == (
        "path_not_allowed"
    )


def timeline_state(harness: Harness) -> dict[str, Any]:
    state = ProjectState(
        media_info=media(harness.source),
        transcript=[sentence(0)],
        video_segments=[
            VideoSegment(
                clip_id="v1",
                source_in_frame=0,
                source_out_frame=25,
                timeline_in_frame=0,
                timeline_out_frame=25,
            )
        ],
        audio_segments=[
            AudioSegment(
                clip_id="v1",
                source_in_sample=0,
                source_out_sample=48000,
                timeline_in_sample=0,
                timeline_out_sample=48000,
            )
        ],
    )
    path = harness.output / "project_state.json"
    path.write_text(state.model_dump_json(), encoding="utf-8")
    return {"state_path": str(path), "shorts": [], "broll_plan": {"Short 1": [{"p": "a"}]}}


def test_timeline_editing_and_export_success(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server
    harness.load()
    harness.write_state()
    harness.pipeline()
    result = timeline_state(harness)
    harness.manager.job.result = result
    (harness.output / "review.json").write_text('{"checks": []}', encoding="utf-8")

    edited = call(
        server,
        "videoflow_edit_timeline",
        {"clip_id": "v1", "action": "move", "delta_sec": 0.1},
    )
    assert edited["ok"] is True
    assert edited["revision"] == 2

    overlay = call(
        server,
        "videoflow_add_timeline_overlay",
        {"path": str(harness.source), "start_sec": 0.0, "duration_sec": 1.0},
    )
    assert overlay["ok"] is True
    overlay_id = overlay["overlay"]["overlay_id"]
    removed = call(server, "videoflow_remove_timeline_overlay", {"overlay_id": overlay_id})
    assert removed["ok"] is True

    comment = call(server, "videoflow_add_clip_comment", {"clip_id": "v1", "text": "tight"})
    assert comment["ok"] is True
    comment_id = comment["comment"]["id"]
    assert call(server, "videoflow_list_clip_comments", {"clip_id": "v1"})["comments"]
    assert call(server, "videoflow_remove_clip_comment", {"comment_id": comment_id})[
        "deleted"
    ] == comment_id

    assert call(
        server, "videoflow_approve_broll", {"title": "Short 1", "approved": [0]}
    )["ok"] is True
    assert call(server, "videoflow_decide_review", {"approved": True})["ok"] is True

    timeline = call(server, "videoflow_get_timeline", {})
    assert timeline["ok"] is True
    assert timeline["video"][0]["clip_id"] == "v1"
    assert timeline["fps"] == 30.0
    assert isinstance(call(server, "videoflow_validate_exports", {}), dict)

    def fake_export(state_arg: Any, directory: Path, *, targets: list[str], dialect: str = ""):
        target = Path(directory) / server_module.FILENAMES[targets[0]]
        target.write_text("exported", encoding="utf-8")
        return {targets[0]: target}

    monkeypatch.setattr(server_module, "export_timeline", fake_export)
    assert call(server, "videoflow_configure_zooms", {})["ok"] is True
    exported = call(
        server,
        "videoflow_export_fcpxml",
        {"output_path": str(harness.tmp / "timeline.fcpxml")},
    )
    assert exported["ok"] is True
    assert exported["size_bytes"] > 0
    assert "warning" in exported
    assert call(
        server,
        "videoflow_run_pipeline",
        {"source": str(harness.source), "output": str(harness.output)},
    )["ok"] is True
    clean = call(
        server,
        "videoflow_export_fcpxml",
        {"output_path": str(harness.tmp / "clean.fcpxml")},
    )
    assert clean["ok"] is True
    assert "warning" not in clean
    assert call(
        server,
        "videoflow_export_fcpxml",
        {"output_path": str(harness.tmp / "x"), "target_nle": "avid"},
    )["code"] == ("invalid_arguments")

    monkeypatch.setattr(
        server_module,
        "resolve_allowed",
        lambda *a, **k: (_ for _ in ()).throw(VideoFlowError("blocked")),
    )
    assert call(
        server, "videoflow_export_fcpxml", {"output_path": str(harness.tmp / "y")}
    )["code"] == ("videoflow_error")


def test_recipe_pipeline_and_batch_success(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server
    recipe = {
        "schema_version": 1,
        "id": "mcp_happy",
        "name": "MCP happy",
        "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
    }
    assert call(server, "videoflow_get_recipe", {"recipe_id": "youtube_talking_head"})[
        "ok"
    ] is True
    assert call(server, "videoflow_validate_recipe", {"recipe": recipe})["order"] == ["ingest"]
    assert call(server, "videoflow_save_recipe", {"recipe": recipe})["ok"] is True
    monkeypatch.setattr(
        server_module, "parse_recipe", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad"))
    )
    assert call(server, "videoflow_validate_recipe", {"recipe": recipe})["code"] == (
        "recipe_invalid"
    )
    monkeypatch.undo()
    monkeypatch.setattr(FFmpegAdapter, "probe", lambda self, path: media(Path(path)))
    monkeypatch.setenv(ROOTS_ENV, str(harness.tmp))

    assert call(
        server,
        "videoflow_run_recipe",
        {"recipe_id": "youtube_talking_head", "source": str(harness.source)},
    )["ok"] is True
    assert harness.manager.job.options["mode"] == "recipe"

    assert call(
        server,
        "videoflow_run_recipe_inline",
        {"recipe": {**recipe, "steps": [{"id": "a", "type": "bogus"}]}, "source": str(
            harness.source
        )},
    )["code"] == ("recipe_invalid")
    assert call(
        server,
        "videoflow_run_step",
        {"step_id": "ingest", "recipe": recipe, "source": str(harness.source)},
    )["ok"] is True

    batch_dir = harness.tmp / "batch-in"
    batch_dir.mkdir()
    (batch_dir / "one.mp4").write_bytes(b"x")
    assert call(
        server,
        "videoflow_run_batch",
        {
            "recipe": recipe,
            "source_dir": str(batch_dir),
            "output_root": str(harness.tmp / "batch-out"),
        },
    )["ok"] is True

    assert call(
        server,
        "videoflow_run_pipeline",
        {"source": str(harness.source), "preset_name": "nope"},
    )["code"] == ("invalid_overrides")
    started = call(
        server,
        "videoflow_run_pipeline",
        {"source": str(harness.source), "output": str(harness.output)},
    )
    job = call(server, "videoflow_get_job", {"job_id": started["job"]["job_id"]})
    assert job["ok"] is True
    assert call(server, "videoflow_get_batch", {"batch_id": "batch-1"})["ok"] is True
    assert call(server, "videoflow_cancel_batch", {"batch_id": "batch-1"})["ok"] is True
    harness.manager.job = FakeJob(harness.source, harness.output, job_id="other")
    assert call(server, "videoflow_get_job", {"job_id": "other"})["ok"] is True
    assert call(
        server,
        "videoflow_run_step",
        {"step_id": "ingest", "recipe_id": "missing", "source": str(harness.source)},
    )["code"] == ("recipe_invalid")

    fresh = Harness(monkeypatch, harness.tmp / "step-fresh")
    assert call(fresh.server, "videoflow_run_step", {"step_id": "ingest", "recipe": recipe})[
        "code"
    ] == ("source_required")


def test_mcp_validate_recipe_names_the_failing_step(harness: Harness) -> None:
    recipe = {
        "schema_version": 1,
        "id": "mcp_bad_params",
        "name": "MCP bad params",
        "steps": [
            {"id": "ingest", "type": "ingest", "params": {}},
            {
                "id": "vad",
                "type": "audio.vad",
                "needs": ["ingest"],
                "params": {"min_silence_ms": -5},
            },
        ],
    }
    result = call(harness.server, "videoflow_validate_recipe", {"recipe": recipe})
    assert result["code"] == "recipe_invalid"
    assert result["message"].startswith("vad:")


def test_resources_prompts_and_whisper_sibling(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = harness.server

    class FakeWhisper:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def transcribe(self, wav: Path, rate: int) -> list[Sentence]:
            return [sentence(0, "From whisper.")]

    monkeypatch.setattr(FFmpegAdapter, "extract_pcm", lambda self, *a, **k: harness.source)
    monkeypatch.setattr(server_module, "WhisperCliAdapter", FakeWhisper)
    default_model = harness.tmp / "default" / "ggml-tiny.bin"
    default_model.parent.mkdir()
    default_model.write_bytes(b"m")
    sibling = default_model.parent / "ggml-small.bin"
    sibling.write_bytes(b"m")
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_MODEL", str(default_model))

    harness.load()
    transcribed = call(server, "videoflow_transcribe", {"engine": "whisper.cpp", "model": "small"})
    assert transcribed["ok"] is True
    assert transcribed["model"] == str(sibling)

    cached = call(server, "videoflow_get_transcript", {"include_word_timestamps": False})
    assert cached["ok"] is True
    assert "words" not in cached["transcript"][0]

    harness.write_state(transcript=[sentence(0)])
    harness.pipeline()
    state_payload = json.loads(read(server, "videoflow://project/state"))
    assert state_payload["transcript"][0]["text"] == "A sentence."
    transcript_payload = read(server, "videoflow://project/transcript")
    assert "From whisper." in transcript_payload
    assert json.loads(read(server, "videoflow://project/exports"))["code"] == (
        "exports_not_found"
    )
    (harness.output / "run.json").write_text(
        json.dumps({"artifacts": {"resolve": str(harness.tmp / "missing.fcpxml")}}),
        encoding="utf-8",
    )
    exports = json.loads(read(server, "videoflow://project/exports"))
    assert exports["exports"]["resolve"]["exists"] is False
    integrations = json.loads(read(server, "videoflow://docs/integrations"))
    assert integrations["ok"] is True

    monkeypatch.setattr(
        FFmpegAdapter,
        "render_thumbnail",
        lambda self, source, target, time_sec=0.0: Path(target).write_bytes(b"jpg"),
    )
    state = ProjectState(media_info=media(harness.source), transcript=[sentence(0)])
    state_path = harness.output / "project_state.json"
    state_path.write_text(state.model_dump_json(), encoding="utf-8")
    harness.manager.job.result = {"state_path": str(state_path), "shorts": []}
    first = call(server, "videoflow_render_frame", {"time_sec": 0.5})
    second = call(server, "videoflow_render_frame", {"time_sec": 0.5})
    assert first["path"] == second["path"]


def test_granular_validation_and_adapter_branches(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    server = harness.server
    assert call(server, "videoflow_run_vad", {})["code"] == "source_required"
    assert call(server, "videoflow_transcribe", {})["code"] == "source_required"
    assert call(server, "videoflow_apply_jcuts", {})["ok"] is True

    invalid_shorts = [
        {"min_duration": 0},
        {"min_duration": 10, "max_duration": 5},
        {"aspect_ratio": "4:3"},
        {"prompt_mode": "bad"},
        {"hook_mode": "bad"},
        {"reframe_mode": "bad"},
        {"start_sec": 5, "end_sec": 1},
        {"count": 0},
        {"count": 1, "min_count": 2},
        {"selection_mode": "bad"},
    ]
    for arguments in invalid_shorts:
        payload = call(server, "videoflow_generate_shorts", arguments)
        assert payload["code"] == "invalid_arguments", arguments

    harness.load()
    monkeypatch.setattr(FFmpegAdapter, "extract_pcm", lambda self, *a, **k: harness.source)
    monkeypatch.setattr(
        server_module,
        "detect_vad",
        lambda *a, **k: SimpleNamespace(spans=[(0, 48000)], engine="ffmpeg"),
    )
    vad = call(server, "videoflow_run_vad", {"vad_engine": "ffmpeg"})
    assert vad["ok"] is True
    assert vad["interval_count"] == 1
    assert vad["vad_engine"] == "ffmpeg"
    assert vad["silence_seconds"] > 0

    class FakeFaster:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def transcribe(self, wav: Path, rate: int) -> list[Sentence]:
            return [sentence(0, "Faster.")]

    class FakeWhisper:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def transcribe(self, wav: Path, rate: int) -> list[Sentence]:
            return [sentence(0, "Whisper.")]

    monkeypatch.setattr(FFmpegAdapter, "extract_pcm", lambda self, *a, **k: harness.source)
    monkeypatch.setattr(server_module, "FasterWhisperAdapter", FakeFaster)
    monkeypatch.setattr(server_module, "WhisperCliAdapter", FakeWhisper)
    model_dir = harness.tmp / "faster" / "small"
    model_dir.mkdir(parents=True)
    monkeypatch.setattr(
        server_module, "find_faster_whisper_model", lambda model: model_dir
    )
    found = call(server, "videoflow_transcribe", {"engine": "faster-whisper"})
    assert found["ok"] is True
    assert found["model"] == str(model_dir)

    default_model = harness.tmp / "whisper" / "ggml-tiny.bin"
    default_model.parent.mkdir()
    default_model.write_bytes(b"m")
    monkeypatch.setenv("VIDEOWFLOW_WHISPER_MODEL", str(default_model))
    fallback = call(
        server, "videoflow_transcribe", {"engine": "whisper.cpp", "model": "medium"}
    )
    assert fallback["ok"] is True
    assert fallback["model"] == str(default_model)
    empty_model = call(
        server, "videoflow_transcribe", {"engine": "whisper.cpp", "model": ""}
    )
    assert empty_model["ok"] is True
    assert empty_model["model"] == str(default_model)
