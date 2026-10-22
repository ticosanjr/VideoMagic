from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.portable import run_portable
from videoflow.core.recipe import parse_recipe
from videoflow.domain.errors import RecipeError
from videoflow.domain.state import MediaInfo
from videoflow.engine.runner import RecipeRunner
from videoflow.steps import requirements_by_type, step_types


class FakeAdapter:
    def __init__(self, speech: list[tuple[int, int]] | None = None) -> None:
        self.speech = speech if speech is not None else [(0, 48000), (96000, 144000)]
        self.detect_calls = 0

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
        self.detect_calls += 1
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
        fontsdir: str | None = None,
        audio_filters: object = None,
        overlay_path: Path | None = None,
        overlay_position: str = "bottom_right",
        overlay_margin: int = 32,
        overlay_width_ratio: float = 0.18,
        overlay_opacity: float = 0.9,
        music_path: Path | None = None,
        music_volume: float = 0.18,
        music_ducking: bool = True,
        music_fade_in_ms: int = 250,
        music_fade_out_ms: int = 500,
        intro_path: Path | None = None,
        outro_path: Path | None = None,
        intro_duration_sec: float = 2.0,
        outro_duration_sec: float = 2.0,
        crop_focus_x: float = 0.5,
        crop_focus_y: float = 0.5,
        split_screen: bool = False,
        split_screen_zoom: float = 1.0,
        split_screen_focus_left: float = 0.5,
        split_screen_focus_right: float = 0.5,
        second_source_path: Path | None = None,
        broll_path: Path | None = None,
        broll_start_sec: float = 0.0,
        broll_duration_sec: float = 2.0,
    ) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"mp4")
        return destination


def srt(path: Path, *, repeat: bool = False) -> Path:
    second = "Same line." if repeat else "A different ending."
    path.write_text(
        f"1\n00:00:00,000 --> 00:00:01,000\nSame line.\n\n"
        f"2\n00:00:02,000 --> 00:00:03,000\n{second}\n",
        encoding="utf-8",
    )
    return path


def base_steps(transcript: Path, *, shorts: bool = False) -> dict:
    steps = [
        {"id": "ingest", "type": "ingest"},
        {
            "id": "vad",
            "type": "audio.vad",
            "needs": ["ingest"],
            "params": {"engine": "ffmpeg"},
        },
        {
            "id": "transcribe",
            "type": "transcribe",
            "needs": ["ingest"],
            "params": {"mode": "srt", "srt_path": str(transcript)},
        },
        {
            "id": "retakes",
            "type": "retakes.cull",
            "needs": ["vad", "transcribe"],
            "params": {"enabled": True},
        },
        {"id": "timeline", "type": "edit.timeline", "needs": ["vad", "retakes"]},
        {
            "id": "export",
            "type": "export.nle",
            "needs": ["timeline"],
            "params": {"targets": ["resolve"]},
        },
    ]
    if shorts:
        steps.insert(
            5,
            {
                "id": "shorts",
                "type": "shorts.select",
                "needs": ["transcribe"],
                "params": {
                    "target_duration_min_sec": 1,
                    "target_duration_max_sec": 3,
                    "min_clips": 1,
                    "max_clips_to_generate": 1,
                    "selection_mode": "heuristic",
                    "burn_subtitles": True,
                },
            },
        )
        steps.insert(
            6,
            {
                "id": "render",
                "type": "shorts.render",
                "needs": ["shorts"],
                "params": {"burn_subtitles": True},
            },
        )
    return {
        "schema_version": 1,
        "id": "test_recipe",
        "name": "Test recipe",
        "steps": steps,
    }


def test_recipe_validation_rejects_cycles_and_unknown_types(tmp_path: Path) -> None:
    cycle = parse_recipe(
        {
            "id": "cycle",
            "name": "Cycle",
            "steps": [
                {"id": "a", "type": "ingest", "needs": ["b"]},
                {"id": "b", "type": "ingest", "needs": ["a"]},
            ],
        }
    )
    with pytest.raises(RecipeError, match="cycle"):
        cycle.validate_graph(step_types(), requires_by_type=requirements_by_type())
    unknown = parse_recipe(
        {
            "id": "unknown",
            "name": "Unknown",
            "steps": [{"id": "a", "type": "does.not.exist"}],
        }
    )
    with pytest.raises(RecipeError, match="unknown type"):
        unknown.validate_graph(step_types(), requires_by_type=requirements_by_type())


def test_recipe_runner_matches_legacy_timeline(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = srt(tmp_path / "subs.srt", repeat=True)
    recipe = parse_recipe(base_steps(transcript))
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    result = RecipeRunner(recipe, adapter=FakeAdapter()).run(source, tmp_path / "recipe")
    legacy = run_portable(
        source,
        tmp_path / "legacy",
        adapter=FakeAdapter(),  # type: ignore[arg-type]
        vad_engine="ffmpeg",
        transcript_path=transcript,
        cull_retakes=True,
    )
    assert len(result.context.state.video_segments) == len(legacy.state.video_segments)
    assert [
        (segment.source_in_frame, segment.source_out_frame)
        for segment in result.context.state.video_segments
    ] == [
        (segment.source_in_frame, segment.source_out_frame)
        for segment in legacy.state.video_segments
    ]
    assert result.context.state.retake_culls == legacy.state.retake_culls
    assert result.state_path.is_file()
    assert json.loads(result.report_path.read_text())["recipe_id"] == "test_recipe"


def test_recipe_runner_renders_shorts(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = srt(tmp_path / "subs.srt")
    recipe = parse_recipe(base_steps(transcript, shorts=True))
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    result = RecipeRunner(recipe, adapter=FakeAdapter()).run(source, tmp_path / "out")
    assert result.context.shorts
    assert (tmp_path / "out" / "shorts.json").is_file()
    assert Path(str(result.context.shorts[0]["path"])).is_file()


def test_recipe_runner_requires_transcript_for_shorts(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    recipe = parse_recipe(
        {
            "id": "no_transcript",
            "name": "No transcript",
            "steps": [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "vad",
                    "type": "audio.vad",
                    "needs": ["ingest"],
                    "params": {"engine": "ffmpeg"},
                },
                {
                    "id": "transcribe",
                    "type": "transcribe",
                    "needs": ["ingest"],
                    "params": {"mode": "none"},
                },
                {"id": "shorts", "type": "shorts.select", "needs": ["transcribe"]},
            ],
        }
    )
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    with pytest.raises(Exception, match="transcript"):
        RecipeRunner(recipe, adapter=FakeAdapter()).run(source, tmp_path / "out")


def test_recipe_api_lists_steps_and_validates() -> None:
    client = TestClient(create_app())
    steps = client.get("/api/v1/steps")
    assert steps.status_code == 200
    step_types_payload = {item["type"] for item in steps.json()["steps"]}
    assert {"ingest", "shorts.reframe", "shorts.captions", "shorts.render"} <= step_types_payload
    recipes = client.get("/api/v1/recipes")
    assert recipes.status_code == 200
    assert {item["id"] for item in recipes.json()["recipes"]} >= {
        "youtube_talking_head",
        "viral_shorts_batch",
    }
    invalid = client.post(
        "/api/v1/recipes/validate",
        json={
            "id": "cycle",
            "name": "Cycle",
            "steps": [
                {"id": "a", "type": "ingest", "needs": ["b"]},
                {"id": "b", "type": "ingest", "needs": ["a"]},
            ],
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "recipe_invalid"


def test_job_manager_runs_recipe_mode(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.jobs import JobManager

    class FakeRunner:
        def __init__(self, recipe) -> None:
            self.recipe = recipe

        def run(self, source, output, **_kwargs):
            class Result:
                def to_dict(self):
                    return {
                        "ok": True,
                        "mode": "recipe",
                        "recipe_id": self.recipe_id,
                        "artifacts": {},
                        "shorts": [],
                    }

            result = Result()
            result.recipe_id = self.recipe.id
            return result

    monkeypatch.setattr("videoflow.engine.runner.RecipeRunner", FakeRunner)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    recipe = {
        "id": "job_recipe",
        "name": "Job recipe",
        "steps": [{"id": "ingest", "type": "ingest"}],
    }
    manager = JobManager()
    job = manager.start(
        source,
        tmp_path / "out",
        {"mode": "recipe", "recipe": recipe},
    )
    for _ in range(100):
        current = manager.get(str(job.job_id))
        if current.status in {"succeeded", "failed", "cancelled"}:
            break
        import time

        time.sleep(0.01)
    current = manager.get(str(job.job_id))
    assert current.status == "succeeded"
    assert current.result is not None
    assert current.result["recipe_id"] == "job_recipe"


def test_recipe_paths_are_resolved_inside_the_allowlist(tmp_path: Path) -> None:
    from videoflow.domain.errors import PathJailError
    from videoflow.engine.recipes import resolve_recipe_paths

    recipe = parse_recipe(
        {
            "id": "paths",
            "name": "Paths",
            "steps": [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "transcribe",
                    "type": "transcribe",
                    "needs": ["ingest"],
                    "params": {"mode": "srt", "srt_path": "/etc/passwd"},
                },
            ],
        }
    )
    with pytest.raises(PathJailError):
        resolve_recipe_paths(recipe, [tmp_path])


def test_vad_cache_is_reused_across_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    recipe = parse_recipe(
        {
            "id": "cache_vad",
            "name": "Cache VAD",
            "steps": [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "vad",
                    "type": "audio.vad",
                    "needs": ["ingest"],
                    "params": {"engine": "ffmpeg"},
                },
            ],
        }
    )
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    adapter = FakeAdapter()
    first = RecipeRunner(recipe, adapter=adapter).run(source, tmp_path / "one")
    second = RecipeRunner(recipe, adapter=adapter).run(source, tmp_path / "two")
    assert "audio.vad" in first.context.cache_misses
    assert "audio.vad" in second.context.cache_hits
    assert adapter.detect_calls == 1
    assert second.context.speech_intervals == first.context.speech_intervals


class FakeAsr:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, wav: Path, sample_rate: int) -> list:
        self.calls += 1
        from videoflow.domain.state import Sentence

        return [
            Sentence(
                id=0,
                start_sample=0,
                end_sample=48000,
                text="Cached sentence.",
            )
        ]


def test_transcript_cache_is_reused(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    recipe = parse_recipe(
        {
            "id": "cache_asr",
            "name": "Cache ASR",
            "steps": [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "transcribe",
                    "type": "transcribe",
                    "needs": ["ingest"],
                    "params": {"mode": "http", "base_url": "http://127.0.0.1:9/v1"},
                },
            ],
        }
    )
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    client = FakeAsr()
    first = RecipeRunner(recipe, adapter=FakeAdapter(), asr_client=client).run(
        source, tmp_path / "one"
    )
    second = RecipeRunner(recipe, adapter=FakeAdapter(), asr_client=client).run(
        source, tmp_path / "two"
    )
    assert client.calls == 1
    assert "transcribe" in first.context.cache_misses
    assert "transcribe" in second.context.cache_hits
    assert second.context.transcript[0].text == "Cached sentence."


def test_reframe_and_captions_are_independent_steps(monkeypatch, tmp_path: Path) -> None:

    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = tmp_path / "subs.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:03,000\nA complete sentence for captions.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "videoflow.steps.shorts_reframe.track_focus_x",
        lambda *args, **kwargs: (0.25, "motion_tracking"),
    )
    seen: dict[str, object] = {}

    class CapturingAdapter(FakeAdapter):
        def render_short(self, *args, **kwargs):
            seen["ass_path"] = kwargs.get("ass_path")
            seen["crop_focus_x"] = kwargs.get("crop_focus_x")
            return super().render_short(*args, **kwargs)

    recipe = parse_recipe(
        {
            "id": "reframe_captions",
            "name": "Reframe and captions",
            "steps": [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "vad",
                    "type": "audio.vad",
                    "needs": ["ingest"],
                    "params": {"engine": "ffmpeg"},
                },
                {
                    "id": "transcribe",
                    "type": "transcribe",
                    "needs": ["ingest"],
                    "params": {"mode": "srt", "srt_path": str(transcript)},
                },
                {
                    "id": "shorts",
                    "type": "shorts.select",
                    "needs": ["transcribe"],
                    "params": {
                        "target_duration_min_sec": 1,
                        "target_duration_max_sec": 5,
                        "min_clips": 1,
                        "max_clips_to_generate": 1,
                        "selection_mode": "heuristic",
                    },
                },
                {
                    "id": "reframe",
                    "type": "shorts.reframe",
                    "needs": ["shorts"],
                    "params": {"mode": "motion_tracking"},
                },
                {
                    "id": "captions",
                    "type": "shorts.captions",
                    "needs": ["shorts"],
                    "params": {"enabled": True},
                },
                {
                    "id": "render",
                    "type": "shorts.render",
                    "needs": ["reframe", "captions"],
                    "params": {"burn_subtitles": True},
                },
            ],
        }
    )
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    result = RecipeRunner(recipe, adapter=CapturingAdapter()).run(source, tmp_path / "out")
    assert result.context.short_captions
    assert seen["ass_path"] is not None
    assert Path(str(seen["ass_path"])).is_file()
    assert seen["crop_focus_x"] == 0.25
    assert not result.context.cache_hits


def test_second_run_reuses_every_checkpoint(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = srt(tmp_path / "subs.srt")
    recipe = parse_recipe(base_steps(transcript))
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    adapter = FakeAdapter()
    first = RecipeRunner(recipe, adapter=adapter).run(source, tmp_path / "out")
    second = RecipeRunner(recipe, adapter=adapter).run(source, tmp_path / "out")
    assert all(run.status == "executed" for run in first.step_runs)
    assert all(run.status == "cached" for run in second.step_runs)
    assert adapter.detect_calls == 1
    assert (tmp_path / "out" / "exports" / "timeline.fcpxml").is_file()


def test_missing_output_invalidates_only_that_step(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = srt(tmp_path / "subs.srt")
    recipe = parse_recipe(base_steps(transcript))
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    adapter = FakeAdapter()
    RecipeRunner(recipe, adapter=adapter).run(source, tmp_path / "out")
    artifact = tmp_path / "out" / "exports" / "timeline.fcpxml"
    artifact.unlink()
    second = RecipeRunner(recipe, adapter=adapter).run(source, tmp_path / "out")
    by_id = {run.id: run.status for run in second.step_runs}
    assert by_id["export"] == "executed"
    assert by_id["timeline"] == "cached"
    assert artifact.is_file()


def test_run_through_stops_after_target(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = srt(tmp_path / "subs.srt")
    recipe = parse_recipe(base_steps(transcript))
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    result = RecipeRunner(recipe, adapter=FakeAdapter()).run(
        source, tmp_path / "out", through="vad"
    )
    assert [run.id for run in result.step_runs] == ["ingest", "vad"]
    assert not (tmp_path / "out" / "project_state.json").exists()
    assert not (tmp_path / "out" / "exports" / "timeline.fcpxml").exists()


def test_recipe_rejects_missing_upstream_step_type(tmp_path: Path) -> None:
    recipe = parse_recipe(
        {
            "id": "missing_vad",
            "name": "Missing VAD",
            "steps": [
                {"id": "ingest", "type": "ingest"},
                {
                    "id": "transcribe",
                    "type": "transcribe",
                    "needs": ["ingest"],
                    "params": {"mode": "none"},
                },
                {
                    "id": "retakes",
                    "type": "retakes.cull",
                    "needs": ["transcribe"],
                    "params": {"enabled": True},
                },
            ],
        }
    )
    with pytest.raises(RecipeError, match="audio.vad"):
        recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())


def test_step_api_starts_a_through_job(tmp_path: Path) -> None:
    from videoflow.application.jobs import Job

    class FakeJobs:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def start(self, source, output, options=None, **kwargs):
            self.calls.append({"source": source, "output": output, "options": options})
            return Job(source=source, output=output, options=options or {})

    home = tmp_path / "videoflow-home"
    home.mkdir(parents=True)
    source = home / "source.mp4"
    source.write_bytes(b"fixture")
    output = home / "out"
    jobs = FakeJobs()
    client = TestClient(create_app(jobs=jobs))
    recipe = base_steps(srt(home / "subs.srt"))
    response = client.post(
        "/api/v1/steps/vad/run",
        json={
            "source": str(source),
            "output": str(output),
            "recipe": recipe,
        },
    )
    assert response.status_code == 202
    assert jobs.calls[0]["options"]["through"] == "vad"
    assert jobs.calls[0]["options"]["resume"] is True


def test_second_shorts_run_reuses_checkpoints_and_selected_clips(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = srt(tmp_path / "subs.srt")
    recipe = parse_recipe(base_steps(transcript, shorts=True))
    recipe.validate_graph(step_types(), requires_by_type=requirements_by_type())
    adapter = FakeAdapter()
    first = RecipeRunner(recipe, adapter=adapter).run(source, tmp_path / "out")
    second = RecipeRunner(recipe, adapter=adapter).run(source, tmp_path / "out")
    assert first.context.shorts
    assert len(second.context.selected_shorts) == len(first.context.selected_shorts)
    assert second.context.shorts[0]["path"] == first.context.shorts[0]["path"]
    assert all(run.status == "cached" for run in second.step_runs)


def test_broll_plan_reaches_short_render(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = srt(tmp_path / "subs.srt")
    assets = tmp_path / "broll"
    assets.mkdir()
    (assets / "same-line.mp4").write_bytes(b"broll")
    recipe = base_steps(transcript, shorts=True)
    recipe["steps"].insert(
        6,
        {
            "id": "broll",
            "type": "broll.plan",
            "needs": ["shorts"],
            "params": {"asset_dir": str(assets)},
        },
    )
    for step in recipe["steps"]:
        if step["id"] == "render":
            step["needs"] = ["shorts", "broll"]
    parsed = parse_recipe(recipe)
    parsed.validate_graph(step_types(), requires_by_type=requirements_by_type())
    seen: dict[str, object] = {}

    class CapturingAdapter(FakeAdapter):
        def render_short(self, *args, **kwargs):
            seen["broll_path"] = kwargs.get("broll_path")
            return super().render_short(*args, **kwargs)

    result = RecipeRunner(parsed, adapter=CapturingAdapter()).run(source, tmp_path / "out")
    assert result.context.metadata["broll_plan"]
    assert seen["broll_path"] is not None
    assert Path(str(seen["broll_path"])).is_file()


def test_failed_recipe_writes_failure_and_history(monkeypatch, tmp_path: Path) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.domain.errors import IngestError
    from videoflow.engine.history import read_runs

    class FailingRunner:
        def __init__(self, recipe) -> None:
            self.recipe = recipe

        def run(self, source, output, **_kwargs):
            raise IngestError(
                "ffmpeg failed: bad filter",
                command="ffmpeg -filter_complex bad",
                stderr="bad filter graph",
            )

    monkeypatch.setattr("videoflow.engine.runner.RecipeRunner", FailingRunner)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    recipe = {
        "id": "failing_recipe",
        "name": "Failing recipe",
        "steps": [{"id": "ingest", "type": "ingest"}],
    }
    output = tmp_path / "out"
    job = JobManager().start(
        source,
        output,
        {"mode": "recipe", "recipe": recipe},
    )
    import time

    for _ in range(100):
        current = job
        if current.status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.01)
        current = job
    # JobManager mutates the returned Job object in place.
    assert job.status == "failed"
    failure = output / "work" / "failure.json"
    for _ in range(100):
        if failure.is_file() and read_runs(output):
            break
        time.sleep(0.01)
    assert failure.is_file()
    payload = json.loads(failure.read_text())
    assert payload["error"]["command"].startswith("ffmpeg")
    runs = read_runs(output)
    assert runs[-1]["status"] == "failed"
    assert runs[-1]["error"]["code"] == "ingest_failed"
