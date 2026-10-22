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
from videoflow.steps import step_types


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
            "needs": ["transcribe"],
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
        cycle.validate_graph(step_types())
    unknown = parse_recipe(
        {
            "id": "unknown",
            "name": "Unknown",
            "steps": [{"id": "a", "type": "does.not.exist"}],
        }
    )
    with pytest.raises(RecipeError, match="unknown type"):
        unknown.validate_graph(step_types())


def test_recipe_runner_matches_legacy_timeline(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    transcript = srt(tmp_path / "subs.srt", repeat=True)
    recipe = parse_recipe(base_steps(transcript))
    recipe.validate_graph(step_types())
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
    recipe.validate_graph(step_types())
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
                {"id": "shorts", "type": "shorts.select", "needs": ["ingest"]},
            ],
        }
    )
    recipe.validate_graph(step_types())
    with pytest.raises(Exception, match="transcript"):
        RecipeRunner(recipe, adapter=FakeAdapter()).run(source, tmp_path / "out")


def test_recipe_api_lists_steps_and_validates() -> None:
    client = TestClient(create_app())
    steps = client.get("/api/v1/steps")
    assert steps.status_code == 200
    assert "ingest" in {item["type"] for item in steps.json()["steps"]}
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
                {
                    "id": "transcribe",
                    "type": "transcribe",
                    "params": {"mode": "srt", "srt_path": "/etc/passwd"},
                }
            ],
        }
    )
    with pytest.raises(PathJailError):
        resolve_recipe_paths(recipe, [tmp_path])
