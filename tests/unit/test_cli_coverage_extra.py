"""Extra hermetic coverage for the unified CLI command handlers."""

import builtins
import json
import os
import runpy
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from types import SimpleNamespace

import pytest

import videoflow.steps as steps_package
from videoflow import __version__, cli
from videoflow.adapters import llm as llm_module
from videoflow.application import settings as settings_module
from videoflow.application import tracking as tracking_module
from videoflow.application.services import ServiceProcess
from videoflow.application.shorts import ShortClip
from videoflow.domain.state import MediaInfo, Sentence
from videoflow.engine import batch as batch_module
from videoflow.engine import maintenance as maintenance_module
from videoflow.engine import recipes as recipes_module
from videoflow.engine import runner as runner_module
from videoflow.mcp_server import server as mcp_server_module
from videoflow.steps import cache as cache_module


class FakeResult:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self._payload = payload or {"ok": True}

    def to_dict(self) -> dict[str, object]:
        return dict(self._payload)


def _media(source: Path) -> MediaInfo:
    return MediaInfo(
        source_path=str(source),
        duration_frames=300,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )


def _sentences() -> list[Sentence]:
    return [
        Sentence(id=1, start_sample=0, end_sample=48000, text="First line."),
        Sentence(id=2, start_sample=48000, end_sample=96000, text="Second line."),
    ]


def _short_clip(pieces: tuple[tuple[int, int], ...] = ((0, 96000),)) -> ShortClip:
    return ShortClip(
        title="A Great Clip",
        start_sample=0,
        end_sample=96000,
        sentence_ids=(1,),
        pieces=pieces,
    )


def _fake_uvicorn(run) -> SimpleNamespace:
    class Config:
        def __init__(self, app, **kwargs) -> None:
            self.app = app
            self.kwargs = kwargs

    class Server:
        def __init__(self, config) -> None:
            self.config = config

        def run(self) -> None:
            run(self.config.app)

    return SimpleNamespace(Config=Config, Server=Server)


# ---------------------------------------------------------------- demo








# ---------------------------------------------------------------- shorts


def test_shorts_renders_with_captions(monkeypatch, tmp_path, capsys) -> None:
    media = _media(tmp_path / "source.mp4")
    seen: dict[str, object] = {}

    class Adapter:
        def probe(self, path):
            seen["probe"] = path
            return media

        def render_short(self, source, pieces, destination, **kwargs):
            seen["render"] = {
                "source": source,
                "pieces": pieces,
                "destination": destination,
                **kwargs,
            }

    monkeypatch.setattr(cli, "FFmpegAdapter", Adapter)
    monkeypatch.setattr(cli, "parse_srt_file", lambda path, rate: _sentences())
    monkeypatch.setattr(cli, "select_shorts", lambda sentences, **kwargs: [_short_clip()])
    monkeypatch.setattr(cli, "fonts_dir", lambda: tmp_path / "fonts")
    out = tmp_path / "out"
    code = cli.main(
        [
            "shorts",
            str(tmp_path / "source.mp4"),
            "--transcript",
            str(tmp_path / "t.srt"),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["culled_sentence_ids"] == []
    assert payload["transcript"] == str((tmp_path / "t.srt").resolve())
    clip = payload["clips"][0]
    assert clip["aspect_ratio"] == "9:16"
    assert clip["width"] == 1080
    assert clip["height"] == 1920
    assert clip["path"] == str(out / "shorts" / "01-a-great-clip.mp4")
    assert clip["subtitles"].endswith(".ass")
    assert (out / "shorts.json").is_file()
    render = seen["render"]
    assert render["source"] == (tmp_path / "source.mp4").resolve()
    assert render["pieces"] == ((0, 96000),)
    assert render["sample_rate"] == 48000
    assert render["ass_path"] == out / "shorts" / "01-a-great-clip.ass"
    assert render["fontsdir"] == str(tmp_path / "fonts")
    assert render["audio_filters"] == ()


def test_shorts_skips_captions_without_events(monkeypatch, tmp_path, capsys) -> None:
    media = _media(tmp_path / "source.mp4")
    seen: dict[str, object] = {}

    class Adapter:
        def probe(self, path):
            return media

        def render_short(self, source, pieces, destination, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(cli, "FFmpegAdapter", Adapter)
    monkeypatch.setattr(cli, "parse_srt_file", lambda path, rate: _sentences())
    monkeypatch.setattr(
        cli,
        "select_shorts",
        lambda sentences, **kwargs: [_short_clip(pieces=((100000, 196000),))],
    )
    monkeypatch.setattr(cli, "fonts_dir", lambda: tmp_path / "fonts")
    code = cli.main(
        [
            "shorts",
            str(tmp_path / "source.mp4"),
            "--transcript",
            str(tmp_path / "t.srt"),
            "--out",
            str(tmp_path / "out"),
            "--audio-enhance",
            "--aspect",
            "16:9",
        ]
    )
    assert code == 0
    clip = json.loads(capsys.readouterr().out)["clips"][0]
    assert "subtitles" not in clip
    assert (clip["width"], clip["height"]) == (1920, 1080)
    assert seen["ass_path"] is None
    assert seen["audio_filters"]


def test_shorts_explicit_no_subtitles(monkeypatch, tmp_path, capsys) -> None:
    media = _media(tmp_path / "source.mp4")

    class Adapter:
        def probe(self, path):
            return media

        def render_short(self, source, pieces, destination, **kwargs) -> None:
            pass

    monkeypatch.setattr(cli, "FFmpegAdapter", Adapter)
    monkeypatch.setattr(cli, "parse_srt_file", lambda path, rate: _sentences())
    monkeypatch.setattr(cli, "select_shorts", lambda sentences, **kwargs: [_short_clip()])
    monkeypatch.setattr(cli, "fonts_dir", lambda: tmp_path / "fonts")
    code = cli.main(
        [
            "shorts",
            str(tmp_path / "source.mp4"),
            "--transcript",
            str(tmp_path / "t.srt"),
            "--out",
            str(tmp_path / "out"),
            "--no-subtitles",
        ]
    )
    assert code == 0
    clip = json.loads(capsys.readouterr().out)["clips"][0]
    assert "subtitles" not in clip


def _patch_probe(monkeypatch, tmp_path) -> None:
    media = _media(tmp_path / "source.mp4")
    monkeypatch.setattr(
        cli, "FFmpegAdapter", lambda: SimpleNamespace(probe=lambda path: media)
    )


def test_shorts_rejects_inverted_window(monkeypatch, tmp_path, capsys) -> None:
    _patch_probe(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "parse_srt_file", lambda path, rate: _sentences())
    code = cli.main(
        [
            "shorts",
            str(tmp_path / "source.mp4"),
            "--transcript",
            str(tmp_path / "t.srt"),
            "--start-sec",
            "10",
            "--end-sec",
            "5",
        ]
    )
    assert code == 2
    assert "--end-sec must be greater than --start-sec." in capsys.readouterr().err


def test_shorts_rejects_empty_source_window(monkeypatch, tmp_path, capsys) -> None:
    _patch_probe(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "parse_srt_file", lambda path, rate: _sentences())
    code = cli.main(
        [
            "shorts",
            str(tmp_path / "source.mp4"),
            "--transcript",
            str(tmp_path / "t.srt"),
            "--start-sec",
            "100",
            "--end-sec",
            "200",
        ]
    )
    assert code == 1
    assert "No sentences remain" in capsys.readouterr().err


def test_shorts_rejects_invalid_duration_range(monkeypatch, tmp_path, capsys) -> None:
    _patch_probe(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "parse_srt_file", lambda path, rate: _sentences())
    code = cli.main(
        [
            "shorts",
            str(tmp_path / "source.mp4"),
            "--transcript",
            str(tmp_path / "t.srt"),
            "--min-sec",
            "60",
            "--max-sec",
            "30",
        ]
    )
    assert code == 2
    assert "--max-sec must be greater than --min-sec." in capsys.readouterr().err


def test_version_and_unknown_commands(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "__version__", "9.9.9")
    assert cli.main(["version"]) == 0
    assert "videoflow 9.9.9" in capsys.readouterr().out
    assert cli.main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()


def test_shorts_reports_when_no_clips_survive(monkeypatch, tmp_path, capsys) -> None:
    media = _media(tmp_path / "source.mp4")

    class Adapter:
        def probe(self, path):
            return media

    monkeypatch.setattr(cli, "FFmpegAdapter", Adapter)
    monkeypatch.setattr(cli, "parse_srt_file", lambda path, rate: _sentences())
    monkeypatch.setattr(cli, "select_shorts", lambda sentences, **kwargs: [])
    code = cli.main(
        ["shorts", str(tmp_path / "source.mp4"), "--transcript", str(tmp_path / "t.srt")]
    )
    assert code == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["ok"] is False


def test_shorts_handles_llm_retakes_scene_and_tracking(monkeypatch, tmp_path, capsys) -> None:
    media = _media(tmp_path / "source.mp4")
    captured: dict[str, object] = {}

    class Adapter:
        def probe(self, path):
            return media

        def render_short(self, source, pieces, destination, **kwargs):
            captured["render"] = kwargs

    class FakeLlm:
        def __init__(self, **kwargs) -> None:
            captured["llm"] = kwargs

    monkeypatch.setattr(cli, "FFmpegAdapter", Adapter)
    monkeypatch.setattr(cli, "parse_srt_file", lambda path, rate: _sentences())
    monkeypatch.setattr(
        cli,
        "cull_transcript_retakes",
        lambda sentences, client=None: SimpleNamespace(discard_sentence_ids={1}),
    )
    monkeypatch.setattr(cli, "cull_intervals", lambda sentences, ids: [(0, 48000)])
    monkeypatch.setattr(cli, "detect_scene_changes", lambda source: ["change"])
    monkeypatch.setattr(
        cli, "scene_intervals", lambda changes, sample_rate: [(0, 48000)]
    )
    monkeypatch.setattr(cli, "previous_shorts_from_report", lambda path: [])
    monkeypatch.setattr(llm_module, "OpenAICompatibleLlm", FakeLlm)
    monkeypatch.setattr(
        tracking_module, "track_focus_x", lambda *args, **kwargs: (0.25, "face_tracking")
    )
    monkeypatch.setenv("VIDEOWFLOW_LLM_API_KEY", "secret")

    def fake_select(sentences, **kwargs):
        captured["sentences"] = sentences
        captured["select"] = kwargs
        return [_short_clip(pieces=((48000, 96000),))]

    monkeypatch.setattr(cli, "select_shorts", fake_select)
    monkeypatch.setattr(cli, "fonts_dir", lambda: tmp_path / "fonts")
    out = tmp_path / "out"
    code = cli.main(
        [
            "shorts",
            str(tmp_path / "source.mp4"),
            "--transcript",
            str(tmp_path / "t.srt"),
            "--out",
            str(out),
            "--cull-retakes",
            "--scene-change",
            "--reframe",
            "face_tracking",
            "--llm-base-url",
            "http://llm.local/v1",
            "--llm-model",
            "tiny",
            "--prompt-mode",
            "refine",
            "--no-subtitles",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["culled_sentence_ids"] == [1]
    assert payload["clips"][0]["crop_focus_x"] == 0.25
    assert [item.id for item in captured["sentences"]] == [2]
    assert captured["select"]["cuts"] == [(0, 48000)]
    assert captured["select"]["scene_intervals"] == ((0, 48000),)
    assert captured["select"]["previous"] == []
    assert isinstance(captured["select"]["client"], FakeLlm)
    assert captured["llm"] == {
        "base_url": "http://llm.local/v1",
        "model": "tiny",
        "api_key": "secret",
    }
    assert captured["render"]["crop_focus_x"] == 0.25


# ---------------------------------------------------------------- recipe


def test_recipe_list(monkeypatch, capsys) -> None:
    monkeypatch.setattr(recipes_module, "list_recipes", lambda: [{"id": "demo"}])
    assert cli.main(["recipe", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "recipes": [{"id": "demo"}],
    }


def test_recipe_steps(monkeypatch, capsys) -> None:
    monkeypatch.setattr(steps_package, "manifest", lambda: [{"id": "ingest"}])
    assert cli.main(["recipe", "steps"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "steps": [{"id": "ingest"}],
    }


def test_recipe_show(capsys) -> None:
    assert cli.main(["recipe", "show", "youtube_talking_head"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "youtube_talking_head"
    assert payload["steps"]


def test_recipe_validate(tmp_path, capsys) -> None:
    recipe = recipes_module.get_recipe("youtube_talking_head")
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(recipe.model_dump(mode="json")), encoding="utf-8")
    assert cli.main(["recipe", "validate", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["recipe"] == "youtube_talking_head"
    assert "ingest" in payload["order"]


def test_recipe_without_subcommand(capsys) -> None:
    assert cli.main(["recipe"]) == 2
    assert "videoflow recipe" in capsys.readouterr().err


def test_recipe_run_dry_run_with_variables(monkeypatch, tmp_path, capsys) -> None:
    instances: list[object] = []

    class FakeRunner:
        def __init__(self, recipe):
            self.recipe = recipe
            self.plan_kwargs = None
            instances.append(self)

        def plan(self, **kwargs):
            self.plan_kwargs = kwargs
            return {"ok": True, "steps": []}

    monkeypatch.setattr(runner_module, "RecipeRunner", FakeRunner)
    source = tmp_path / "source.mp4"
    code = cli.main(
        [
            "recipe",
            "run",
            "youtube_talking_head",
            str(source),
            "--dry-run",
            "--profile",
            "fast",
            "--var",
            "retries=3",
            "--var",
            "label=plain",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "steps": []}
    assert instances[0].plan_kwargs == {
        "variables": {"retries": 3, "label": "plain"},
        "profile": "fast",
    }


def test_recipe_run_prints_progress_and_report(monkeypatch, tmp_path, capsys) -> None:
    instances: list[object] = []

    class FakeRunner:
        def __init__(self, recipe):
            self.recipe = recipe
            instances.append(self)

        def run(self, source, output, **kwargs):
            self.run_kwargs = {"source": source, "output": output, **kwargs}
            kwargs["progress"]("ingest", 42, "worked")
            return FakeResult({"ok": True, "recipe_id": self.recipe.id})

    monkeypatch.setattr(runner_module, "RecipeRunner", FakeRunner)
    source = tmp_path / "source.mp4"
    assert cli.main(["recipe", "run", "youtube_talking_head", str(source)]) == 0
    captured = capsys.readouterr()
    assert captured.err == "[ 42%] ingest: worked\n"
    assert json.loads(captured.out)["ok"] is True
    assert instances[0].run_kwargs["output"] == source.with_name("source-videoflow")
    assert instances[0].run_kwargs["resume"] is True
    assert instances[0].run_kwargs["variables"] == {}
    assert instances[0].run_kwargs["profile"] is None

    assert (
        cli.main(
            ["recipe", "run", "youtube_talking_head", str(source), "--json", "--force"]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert instances[-1].run_kwargs["resume"] is False
    assert instances[-1].run_kwargs["progress"] is not None


def test_recipe_run_rejects_invalid_variable(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(runner_module, "RecipeRunner", lambda recipe: None)
    assert (
        cli.main(
            [
                "recipe",
                "run",
                "youtube_talking_head",
                str(tmp_path / "source.mp4"),
                "--var",
                "novalue",
            ]
        )
        == 2
    )
    assert "expected KEY=VALUE" in capsys.readouterr().err


def test_recipe_step_runs_through_a_step(monkeypatch, tmp_path, capsys) -> None:
    instances: list[object] = []

    class FakeRunner:
        def __init__(self, recipe):
            self.recipe = recipe
            instances.append(self)

        def run(self, source, output, **kwargs):
            self.run_kwargs = {"source": source, "output": output, **kwargs}
            kwargs["progress"]("ingest", 7, "step")
            return FakeResult({"ok": True})

    monkeypatch.setattr(runner_module, "RecipeRunner", FakeRunner)
    source = tmp_path / "clip.mp4"
    base = [
        "recipe",
        "step",
        "youtube_talking_head",
        "ingest",
        str(source),
        "--force",
    ]
    assert cli.main(base) == 0
    captured = capsys.readouterr()
    assert captured.err == "[  7%] ingest: step\n"
    assert json.loads(captured.out)["ok"] is True
    assert instances[-1].run_kwargs["through"] == "ingest"
    assert instances[-1].run_kwargs["resume"] is False
    assert instances[-1].run_kwargs["variables"] == {}

    assert cli.main(base + ["--json"]) == 0
    assert capsys.readouterr().err == ""


def test_recipe_batch_polls_until_terminal(monkeypatch, tmp_path, capsys) -> None:
    captured: dict[str, object] = {}

    class FakeBatch:
        def __init__(self, status, completed=1, message="Working"):
            self.status = status
            self.completed = completed
            self.message = message
            self.items = ["a", "b"]
            self.batch_id = "batch-1"

        def to_dict(self):
            return {"batch_id": self.batch_id, "status": self.status}

    class FakeBatches:
        def __init__(self, jobs):
            self.jobs = jobs
            captured["jobs"] = jobs

        def start(self, *args, **kwargs):
            captured["start_args"] = args
            captured["start_kwargs"] = kwargs
            return FakeBatch("running")

        def get(self, batch_id):
            captured["polled"] = batch_id
            return FakeBatch("succeeded", completed=2, message="Done")

        def cancel(self, batch_id):
            captured["cancelled"] = batch_id

    monkeypatch.setattr(batch_module, "BatchManager", FakeBatches)
    sleeps: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", sleeps.append)
    source_dir = tmp_path / "src"
    code = cli.main(["recipe", "batch", "youtube_talking_head", str(source_dir)])
    assert code == 0
    captured_io = capsys.readouterr()
    assert "[1/2] running: Working" in captured_io.err
    assert json.loads(captured_io.out) == {
        "ok": True,
        "batch": {"batch_id": "batch-1", "status": "succeeded"},
    }
    assert captured["polled"] == "batch-1"
    assert sleeps == [0.5]
    start_args = captured["start_args"]
    assert start_args[0] == source_dir
    assert start_args[1] == source_dir / "videoflow-batch"
    assert start_args[2]["id"] == "youtube_talking_head"
    assert captured["start_kwargs"]["recipe_id"] == "youtube_talking_head"
    assert captured["start_kwargs"]["recursive"] is False
    assert captured["start_kwargs"]["extensions"] == []
    assert captured["start_kwargs"]["resume"] is True
    assert captured["start_kwargs"]["max_files"] == 200


def test_recipe_batch_quiet_options_and_interrupt(monkeypatch, tmp_path, capsys) -> None:
    captured: dict[str, object] = {}

    class FakeBatch:
        def __init__(self, status):
            self.status = status
            self.completed = 1
            self.message = "Working"
            self.items = ["a"]
            self.batch_id = "batch-2"

        def to_dict(self):
            return {"batch_id": self.batch_id, "status": self.status}

    class InterruptBatches:
        def __init__(self, jobs):
            self.jobs = jobs

        def start(self, *args, **kwargs):
            captured["start_kwargs"] = kwargs
            return FakeBatch("running")

        def get(self, batch_id):
            raise KeyboardInterrupt

        def cancel(self, batch_id):
            captured["cancelled"] = batch_id

    monkeypatch.setattr(batch_module, "BatchManager", InterruptBatches)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    source_dir = tmp_path / "src"
    code = cli.main(
        [
            "recipe",
            "batch",
            "youtube_talking_head",
            str(source_dir),
            "-o",
            str(tmp_path / "out"),
            "--recursive",
            "--extensions",
            "mp4, mov",
            "--max-files",
            "5",
            "--force",
            "--json",
        ]
    )
    assert code == 0
    captured_io = capsys.readouterr()
    assert captured_io.err == ""
    assert json.loads(captured_io.out)["batch"]["status"] == "running"
    assert captured["cancelled"] == "batch-2"
    kwargs = captured["start_kwargs"]
    assert kwargs["recursive"] is True
    assert kwargs["extensions"] == ["mp4", "mov"]
    assert kwargs["max_files"] == 5
    assert kwargs["resume"] is False


def test_recipe_cache_path(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cache_module, "cache_dir", lambda: tmp_path / "cache")
    assert cli.main(["recipe", "cache", "path"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "path": str(tmp_path / "cache")}


def test_recipe_cache_clear(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cache_module, "clear_cache", lambda: 7)
    assert cli.main(["recipe", "cache", "clear"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "removed": 7}


def test_recipe_cache_prune_explicit_paths(monkeypatch, tmp_path, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_prune_output(path, **kwargs):
        captured["output"] = (path, kwargs)
        return {"removed": 1}

    def fake_prune_cache(**kwargs):
        captured["cache"] = kwargs
        return {"removed": 2}

    monkeypatch.setattr(maintenance_module, "prune_output", fake_prune_output)
    monkeypatch.setattr(cache_module, "prune_cache", fake_prune_cache)
    out = tmp_path / "out"
    assert (
        cli.main(
            [
                "recipe",
                "cache",
                "prune",
                "--output",
                str(out),
                "--global-cache",
                "--dry-run",
                "--keep-days",
                "3",
                "--keep-steps",
                "4",
                "--keep-runs",
                "5",
                "--cache-days",
                "6",
                "--cache-max-mb",
                "7",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": True,
        "output": {"removed": 1},
        "global_cache": {"removed": 2},
    }
    assert captured["output"] == (
        out,
        {"keep_days": 3, "keep_steps": 4, "keep_runs": 5, "dry_run": True},
    )
    assert captured["cache"] == {
        "max_age_days": 6,
        "max_bytes": 7 * 1024 * 1024,
        "dry_run": True,
    }


def test_recipe_cache_prune_defaults_to_global_cache(monkeypatch, tmp_path, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_prune_cache(**kwargs):
        captured["cache"] = kwargs
        return {}

    monkeypatch.setattr(cache_module, "prune_cache", fake_prune_cache)
    assert cli.main(["recipe", "cache", "prune"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "global_cache": {}}
    assert captured["cache"] == {
        "max_age_days": 30,
        "max_bytes": 512 * 1024 * 1024,
        "dry_run": False,
    }
    assert cli.main(["recipe", "cache", "prune", "--output", str(tmp_path / "out2")]) == 0
    output_only = json.loads(capsys.readouterr().out)
    assert "global_cache" not in output_only
    assert "output" in output_only


# ---------------------------------------------------------------- serve


def test_serve_applies_settings_and_releases_lock(monkeypatch, tmp_path) -> None:
    fake_os = SimpleNamespace(environ={}, getpid=lambda: 4242)
    released: list[int] = []
    logs: list[str] = []

    class FakeLock:
        def __init__(self, port):
            self.port = port

        def acquire(self):
            return True

        def release(self):
            released.append(self.port)

    captured: dict[str, object] = {}

    def fake_locked(args, uvicorn, create_http_app):
        captured["host"] = args.host
        captured["port"] = args.port
        captured["open"] = args.open
        return 7

    monkeypatch.setattr(cli, "os", fake_os)
    monkeypatch.setattr(cli, "ensure_home", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(Config=object, Server=object))
    monkeypatch.setattr(cli, "_InstanceLock", FakeLock)
    monkeypatch.setattr(cli, "_serve_locked", fake_locked)
    monkeypatch.setattr(cli, "append_server_log", logs.append)
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: settings_module.AppSettings(
            runtime=settings_module.RuntimeSettings(
                host="0.0.0.0", port=9001, open_browser=True
            ),
            paths=settings_module.PathSettings(temp_dir=str(tmp_path / "tmp")),
        ),
    )
    assert cli.main(["serve"]) == 7
    assert captured == {"host": "0.0.0.0", "port": 9001, "open": True}
    assert released == [9001]
    assert fake_os.environ["VIDEOWFLOW_HOME"] == str(tmp_path)
    assert fake_os.environ["TMPDIR"] == str(tmp_path / "tmp")
    assert logs == ["serve requested host=0.0.0.0 port=9001 pid=4242"]


def test_serve_reports_an_already_running_service(monkeypatch, tmp_path, capsys) -> None:
    opened: list[str] = []

    class FakeLock:
        def __init__(self, port):
            self.port = port

        def acquire(self):
            return False

    monkeypatch.setattr(cli, "os", SimpleNamespace(environ={}, getpid=lambda: 1))
    monkeypatch.setattr(cli, "ensure_home", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(Config=object, Server=object))
    monkeypatch.setitem(
        sys.modules, "webbrowser", SimpleNamespace(open=lambda url: opened.append(url))
    )
    monkeypatch.setattr(cli, "_InstanceLock", FakeLock)
    monkeypatch.setattr(cli, "_wait_for_health", lambda host, port, *, timeout: True)
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: settings_module.AppSettings(
            runtime=settings_module.RuntimeSettings(open_browser=True)
        ),
    )
    assert cli.main(["serve"]) == 0
    out = capsys.readouterr().out
    assert "already running at http://127.0.0.1:8765/" in out
    assert opened == [f"http://127.0.0.1:8765/?v={__version__}"]


def test_serve_reports_an_already_running_service_without_browser(
    monkeypatch, tmp_path, capsys
) -> None:
    class FakeLock:
        def __init__(self, port):
            self.port = port

        def acquire(self):
            return False

    monkeypatch.setattr(cli, "os", SimpleNamespace(environ={}, getpid=lambda: 1))
    monkeypatch.setattr(cli, "ensure_home", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(Config=object, Server=object))
    monkeypatch.setattr(cli, "_InstanceLock", FakeLock)
    monkeypatch.setattr(cli, "_wait_for_health", lambda host, port, *, timeout: True)
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: settings_module.AppSettings(
            runtime=settings_module.RuntimeSettings(open_browser=False)
        ),
    )
    assert cli.main(["serve"]) == 0
    assert "already running" in capsys.readouterr().out


def test_serve_fails_when_another_start_never_becomes_ready(
    monkeypatch, tmp_path, capsys
) -> None:
    calls: list[float] = []

    class FakeLock:
        def __init__(self, port):
            self.port = port

        def acquire(self):
            return False

    def fake_wait(host, port, *, timeout):
        calls.append(timeout)
        return False

    monkeypatch.setattr(cli, "os", SimpleNamespace(environ={}, getpid=lambda: 1))
    monkeypatch.setattr(cli, "ensure_home", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(Config=object, Server=object))
    monkeypatch.setattr(cli, "_InstanceLock", FakeLock)
    monkeypatch.setattr(cli, "_wait_for_health", fake_wait)
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: settings_module.AppSettings(
            runtime=settings_module.RuntimeSettings(open_browser=False)
        ),
    )
    assert cli.main(["serve"]) == 1
    captured = capsys.readouterr()
    assert "already in progress" in captured.out
    assert "did not become ready" in captured.err
    assert calls == [1.5, 30.0]


def _settings(monkeypatch, **runtime) -> None:
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: settings_module.AppSettings(
            runtime=settings_module.RuntimeSettings(**runtime)
        ),
    )


def test_serve_keeps_explicit_host_and_port(monkeypatch, tmp_path) -> None:
    released: list[int] = []
    captured: dict[str, object] = {}

    class FakeLock:
        def __init__(self, port):
            self.port = port

        def acquire(self):
            return True

        def release(self):
            released.append(self.port)

    def fake_locked(args, uvicorn, create_http_app):
        captured.update(host=args.host, port=args.port)
        return 0

    monkeypatch.setattr(cli, "os", SimpleNamespace(environ={}, getpid=lambda: 1))
    monkeypatch.setattr(cli, "ensure_home", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(Config=object, Server=object))
    monkeypatch.setattr(cli, "_InstanceLock", FakeLock)
    monkeypatch.setattr(cli, "_serve_locked", fake_locked)
    monkeypatch.setattr(cli, "append_server_log", lambda message: None)
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: settings_module.AppSettings(),
    )
    assert cli.main(["serve", "--host", "203.0.113.5", "--port", "9002"]) == 0
    assert captured == {"host": "203.0.113.5", "port": 9002}
    assert released == [9002]


def test_serve_waits_for_a_slow_start_and_opens_the_browser(
    monkeypatch, tmp_path, capsys
) -> None:
    opened: list[str] = []
    waits: list[float] = []
    responses = iter([False, True])

    class FakeLock:
        def __init__(self, port):
            self.port = port

        def acquire(self):
            return False

    def fake_wait(host, port, *, timeout):
        waits.append(timeout)
        return next(responses)

    monkeypatch.setattr(cli, "os", SimpleNamespace(environ={}, getpid=lambda: 1))
    monkeypatch.setattr(cli, "ensure_home", lambda: tmp_path)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(Config=object, Server=object))
    monkeypatch.setitem(
        sys.modules, "webbrowser", SimpleNamespace(open=lambda url: opened.append(url))
    )
    monkeypatch.setattr(cli, "_InstanceLock", FakeLock)
    monkeypatch.setattr(cli, "_wait_for_health", fake_wait)
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: settings_module.AppSettings(
            runtime=settings_module.RuntimeSettings(open_browser=True)
        ),
    )
    assert cli.main(["serve"]) == 0
    assert waits == [1.5, 30.0]
    assert opened == [f"http://127.0.0.1:8765/?v={__version__}"]
    assert "already in progress" in capsys.readouterr().out

    responses = iter([False, True])
    monkeypatch.setattr(
        settings_module,
        "load_settings",
        lambda: settings_module.AppSettings(
            runtime=settings_module.RuntimeSettings(open_browser=False)
        ),
    )
    assert cli.main(["serve"]) == 0
    capsys.readouterr()
    assert opened == [f"http://127.0.0.1:8765/?v={__version__}"]


def test_serve_locked_starts_the_server(monkeypatch, tmp_path, capsys) -> None:
    apps: list[object] = []
    runs: list[object] = []
    logs: list[str] = []
    pids: list[tuple[str, int]] = []
    removed: list[object] = []
    scheduled: list[str] = []

    class App:
        def __init__(self):
            self.state = SimpleNamespace(jobs="jobs", restart_requested=False)

    def factory(jobs=None):
        app = App()
        apps.append(app)
        return app

    def run(app):
        runs.append(app)

    uvicorn = _fake_uvicorn(run)
    _settings(monkeypatch, log_level="warning")
    monkeypatch.setattr(cli, "append_server_log", logs.append)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: None)
    monkeypatch.setattr(cli, "port_is_busy", lambda host, port: False)
    monkeypatch.setattr(cli, "server_log_path", lambda: tmp_path / "server.log")
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(
        cli, "_write_pid", lambda path, host, port: pids.append((host, port))
    )
    monkeypatch.setattr(cli, "_remove_pid", removed.append)
    monkeypatch.setattr(cli, "_schedule_browser", scheduled.append)
    args = SimpleNamespace(host="127.0.0.1", port=9123, open=True)
    assert cli._serve_locked(args, uvicorn, factory) == 0
    assert len(apps) == 1
    assert apps[0].state.port == 9123
    assert apps[0].state.host == "127.0.0.1"
    assert runs == [apps[0]]
    assert pids == [("127.0.0.1", 9123)]
    assert removed == [Path("/tmp/server.pid")]
    assert scheduled == ["http://127.0.0.1:9123/"]
    assert f"Log: {tmp_path / 'server.log'}" in capsys.readouterr().out
    assert logs[0] == "start lock acquired port=9123 pid=" + str(os.getpid())
    assert logs[-1] == f"stopped pid={os.getpid()}"


def test_serve_locked_reports_same_version(monkeypatch, tmp_path, capsys) -> None:
    opened: list[str] = []
    apps: list[object] = []

    def factory(jobs=None):
        apps.append(jobs)
        return None

    monkeypatch.setitem(
        sys.modules, "webbrowser", SimpleNamespace(open=lambda url: opened.append(url))
    )
    _settings(monkeypatch)
    monkeypatch.setattr(cli, "append_server_log", lambda message: None)
    monkeypatch.setattr(
        cli, "probe_service", lambda host, port: {"version": __version__}
    )
    args = SimpleNamespace(host="127.0.0.1", port=8765, open=True)
    assert cli._serve_locked(args, _fake_uvicorn(lambda app: None), factory) == 0
    assert f"VideoFlow {__version__} is already running" in capsys.readouterr().out
    assert apps == []
    assert opened == [f"http://127.0.0.1:8765/?v={__version__}"]
    args.open = False
    assert cli._serve_locked(args, _fake_uvicorn(lambda app: None), factory) == 0
    capsys.readouterr()
    assert opened == [f"http://127.0.0.1:8765/?v={__version__}"]


def test_serve_locked_replaces_an_older_service(monkeypatch, capsys) -> None:
    apps: list[object] = []
    logs: list[str] = []
    stopped: list[tuple[str, int]] = []

    class App:
        def __init__(self):
            self.state = SimpleNamespace(jobs="jobs", restart_requested=False)

    def factory(jobs=None):
        app = App()
        apps.append(app)
        return app

    _settings(monkeypatch)
    monkeypatch.setattr(cli, "append_server_log", logs.append)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: {"version": "0.0.1"})
    monkeypatch.setattr(
        cli,
        "stop_services_on_port",
        lambda host, port: stopped.append((host, port)) or {"free": True},
    )
    monkeypatch.setattr(cli, "port_is_busy", lambda host, port: False)
    monkeypatch.setattr(cli, "server_log_path", lambda: Path("/tmp/server.log"))
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(cli, "_write_pid", lambda path, host, port: None)
    monkeypatch.setattr(cli, "_remove_pid", lambda path: None)
    monkeypatch.setattr(cli, "_schedule_browser", lambda url: None)
    args = SimpleNamespace(host="127.0.0.1", port=8765, open=False)
    uvicorn = _fake_uvicorn(lambda app: None)
    assert cli._serve_locked(args, uvicorn, factory) == 0
    assert stopped == [("127.0.0.1", 8765)]
    assert apps
    assert any("replacing old service version=0.0.1" in item for item in logs)
    assert any("replacement result=" in item for item in logs)
    assert f"stopping it before starting {__version__}" in capsys.readouterr().out


def test_serve_locked_fails_when_old_service_cannot_stop(monkeypatch, capsys) -> None:
    _settings(monkeypatch)
    monkeypatch.setattr(cli, "append_server_log", lambda message: None)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: {"version": "0.0.1"})
    monkeypatch.setattr(
        cli, "stop_services_on_port", lambda host, port: {"free": False}
    )
    args = SimpleNamespace(host="127.0.0.1", port=8765, open=False)
    assert cli._serve_locked(args, _fake_uvicorn(lambda app: None), lambda jobs=None: None) == 1
    assert "Could not stop the older VideoFlow service" in capsys.readouterr().err


def test_serve_locked_frees_a_foreign_port(monkeypatch) -> None:
    apps: list[object] = []
    stopped: list[tuple[str, int]] = []

    class App:
        def __init__(self):
            self.state = SimpleNamespace(jobs="jobs", restart_requested=False)

    def factory(jobs=None):
        app = App()
        apps.append(app)
        return app

    _settings(monkeypatch)
    monkeypatch.setattr(cli, "append_server_log", lambda message: None)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: None)
    monkeypatch.setattr(cli, "port_is_busy", lambda host, port: True)
    monkeypatch.setattr(
        cli,
        "stop_services_on_port",
        lambda host, port: stopped.append((host, port)) or {"free": True},
    )
    monkeypatch.setattr(cli, "server_log_path", lambda: Path("/tmp/server.log"))
    monkeypatch.setattr(cli, "_write_pid", lambda path, host, port: None)
    monkeypatch.setattr(cli, "_remove_pid", lambda path: None)
    args = SimpleNamespace(host="127.0.0.1", port=8765, open=False)
    assert cli._serve_locked(args, _fake_uvicorn(lambda app: None), factory) == 0
    assert stopped == [("127.0.0.1", 8765)]
    assert apps


def test_serve_locked_rejects_a_busy_foreign_port(monkeypatch, capsys) -> None:
    _settings(monkeypatch)
    monkeypatch.setattr(cli, "append_server_log", lambda message: None)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: None)
    monkeypatch.setattr(cli, "port_is_busy", lambda host, port: True)
    monkeypatch.setattr(
        cli, "stop_services_on_port", lambda host, port: {"free": False}
    )
    args = SimpleNamespace(host="127.0.0.1", port=8765, open=False)
    assert cli._serve_locked(args, _fake_uvicorn(lambda app: None), lambda jobs=None: None) == 1
    assert "is already in use by another process" in capsys.readouterr().err


def test_serve_locked_restarts_when_requested(monkeypatch, capsys) -> None:
    apps: list[object] = []

    class App:
        def __init__(self):
            self.state = SimpleNamespace(jobs="jobs", restart_requested=False)

    def factory(jobs=None):
        app = App()
        apps.append(app)
        return app

    runs: list[int] = []

    def run(app):
        runs.append(len(runs))
        app.state.restart_requested = len(runs) == 1

    _settings(monkeypatch)
    monkeypatch.setattr(cli, "append_server_log", lambda message: None)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: None)
    monkeypatch.setattr(cli, "port_is_busy", lambda host, port: False)
    monkeypatch.setattr(cli, "server_log_path", lambda: Path("/tmp/server.log"))
    monkeypatch.setattr(cli, "_write_pid", lambda path, host, port: None)
    monkeypatch.setattr(cli, "_remove_pid", lambda path: None)
    monkeypatch.setattr(cli, "_schedule_browser", lambda url: None)
    args = SimpleNamespace(host="127.0.0.1", port=8765, open=False)
    assert cli._serve_locked(args, _fake_uvicorn(run), factory) == 0
    assert len(apps) == 2
    assert len(runs) == 2
    assert "VideoFlow service restarting..." in capsys.readouterr().out


def test_serve_locked_logs_and_reraises_server_errors(monkeypatch) -> None:
    logs: list[str] = []
    removed: list[object] = []

    class App:
        def __init__(self):
            self.state = SimpleNamespace(jobs="jobs", restart_requested=False)

    def run(app):
        raise RuntimeError("server exploded")

    _settings(monkeypatch)
    monkeypatch.setattr(cli, "append_server_log", logs.append)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: None)
    monkeypatch.setattr(cli, "port_is_busy", lambda host, port: False)
    monkeypatch.setattr(cli, "server_log_path", lambda: Path("/tmp/server.log"))
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(cli, "_write_pid", lambda path, host, port: None)
    monkeypatch.setattr(cli, "_remove_pid", removed.append)
    args = SimpleNamespace(host="127.0.0.1", port=8765, open=False)
    with pytest.raises(RuntimeError, match="server exploded"):
        cli._serve_locked(args, _fake_uvicorn(run), lambda jobs=None: App())
    assert any("Traceback (most recent call last)" in item for item in logs)
    assert removed == [Path("/tmp/server.pid")]


def test_instance_lock_is_exclusive(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "portable_home", lambda: tmp_path)
    first = cli._InstanceLock(8765)
    assert first.acquire() is True
    second = cli._InstanceLock(8765)
    assert second.acquire() is False
    assert second.handle is None
    second.release()
    first.release()
    third = cli._InstanceLock(8765)
    assert third.acquire() is True
    assert (tmp_path / "server-8765.lock").read_text(encoding="utf-8") == str(os.getpid())
    third.release()


def test_wait_for_health_probes_and_times_out(monkeypatch) -> None:
    monkeypatch.setattr(cli, "probe_service", lambda host, port: {"service": "videoflow"})
    assert cli._wait_for_health("127.0.0.1", 8765, timeout=0.5) is True

    ticks = iter([0.0, 0.1, 2.0])
    slept: list[float] = []
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(cli.time, "sleep", slept.append)
    monkeypatch.setattr(cli, "probe_service", lambda host, port: None)
    assert cli._wait_for_health("127.0.0.1", 8765, timeout=1.5) is False
    assert slept == [0.4]


def test_instance_lock_without_fcntl(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fcntl":
            raise ImportError("no fcntl")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    lock = cli._InstanceLock(9000)
    assert lock.acquire() is True
    assert lock.handle is None


def test_instance_lock_handles_an_unwritable_home(monkeypatch, tmp_path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(cli, "portable_home", lambda: blocker)
    lock = cli._InstanceLock(9000)
    assert lock.acquire() is False
    assert lock.acquired is False
    lock.release()


def test_instance_lock_tolerates_write_and_release_errors(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "portable_home", lambda: tmp_path)
    real_open = Path.open

    class BadHandle:
        def __init__(self, handle) -> None:
            self._handle = handle

        def seek(self, *args):
            return self._handle.seek(*args)

        def truncate(self):
            raise OSError("disk full")

        def fileno(self):
            return self._handle.fileno()

        def write(self, value):
            return self._handle.write(value)

        def flush(self) -> None:
            self._handle.flush()

        def close(self) -> None:
            self._handle.close()

    def fake_open(self, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)
        if self.name.endswith(".lock"):
            return BadHandle(handle)
        return handle

    monkeypatch.setattr(Path, "open", fake_open)
    lock = cli._InstanceLock(9000)
    assert lock.acquire() is True

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fcntl":
            raise ImportError("no fcntl")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    lock.release()
    assert lock.handle is None


def test_schedule_browser_opens_when_healthy(monkeypatch) -> None:
    calls: list[tuple[str, float]] = []
    opened: list[str] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        return Response()

    class ImmediateThread:
        def __init__(self, target, daemon=None) -> None:
            self.daemon = daemon
            target()

        def start(self) -> None:
            pass

    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(webbrowser, "open", opened.append)
    cli._schedule_browser("http://127.0.0.1:8765/")
    assert calls == [("http://127.0.0.1:8765/health", 0.8)]
    assert opened == [f"http://127.0.0.1:8765/?v={__version__}"]


def test_schedule_browser_falls_back_after_failures(monkeypatch) -> None:
    opened: list[str] = []
    ticks = iter([0.0, 0.0, 100.0])

    class ImmediateThread:
        def __init__(self, target, daemon=None) -> None:
            self.daemon = daemon
            target()

        def start(self) -> None:
            pass

    def fail(url, timeout):
        raise OSError("down")

    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    monkeypatch.setattr(webbrowser, "open", opened.append)
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    cli._schedule_browser("http://127.0.0.1:8765/")
    assert opened == [f"http://127.0.0.1:8765/?v={__version__}"]


def test_schedule_browser_retries_until_healthy(monkeypatch) -> None:
    opened: list[str] = []
    statuses = iter([503, 200])
    ticks = iter([0.0, 0.0, 0.1])

    class Response:
        def __init__(self, status) -> None:
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class ImmediateThread:
        def __init__(self, target, daemon=None) -> None:
            self.daemon = daemon
            target()

        def start(self) -> None:
            pass

    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, timeout: Response(next(statuses))
    )
    monkeypatch.setattr(webbrowser, "open", opened.append)
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    cli._schedule_browser("http://127.0.0.1:8765/")
    assert opened == [f"http://127.0.0.1:8765/?v={__version__}"]


def test_module_entry_point_prints_usage() -> None:
    path = Path(__file__).resolve().parents[2] / "src" / "videoflow" / "cli.py"
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(path), run_name="__main__")
    assert excinfo.value.code == 2


# ---------------------------------------------------------------- stop/status


class _Alive:
    def __init__(self, *states: bool) -> None:
        self._states = iter(states)

    def __call__(self, pid: int) -> bool:
        return next(self._states, False)


def test_stop_ignores_an_unparseable_pid(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(cli, "_read_pid", lambda path: {"pid": "oops"})
    assert cli.main(["stop"]) == 0
    assert "not running (no PID file)" in capsys.readouterr().out


def test_stop_removes_a_stale_pid(monkeypatch, capsys) -> None:
    removed: list[object] = []
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(cli, "_read_pid", lambda path: {"pid": 10})
    monkeypatch.setattr(cli, "_process_alive", lambda pid: False)
    monkeypatch.setattr(cli, "_remove_pid", removed.append)
    assert cli.main(["stop"]) == 0
    assert removed == [Path("/tmp/server.pid")]
    assert "stale PID file removed" in capsys.readouterr().out


def test_stop_reports_a_signal_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(cli, "_read_pid", lambda path: {"pid": 10})

    def fail(pid, sig):
        raise OSError("not permitted")

    monkeypatch.setattr(cli, "_process_alive", lambda pid: True)
    monkeypatch.setattr(cli.os, "kill", fail)
    assert cli.main(["stop"]) == 1
    assert "Could not stop VideoFlow (PID 10): not permitted" in capsys.readouterr().err


def test_stop_times_out(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(cli, "_read_pid", lambda path: {"pid": 10})
    monkeypatch.setattr(cli, "_process_alive", lambda pid: True)
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: None)
    assert cli.main(["stop", "--timeout", "0"]) == 1
    assert "did not stop within 0.0s (PID 10)" in capsys.readouterr().err


def test_stop_terminates_the_service(monkeypatch, capsys) -> None:
    removed: list[object] = []
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(cli, "_read_pid", lambda path: {"pid": 10})
    monkeypatch.setattr(cli, "_process_alive", _Alive(True, True, False, False))
    monkeypatch.setattr(cli, "_remove_pid", removed.append)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    assert cli.main(["stop"]) == 0
    assert killed == [(10, cli.signal.SIGTERM)]
    assert removed == [Path("/tmp/server.pid")]
    assert "VideoFlow service stopped (PID 10)." in capsys.readouterr().out


def test_status_lists_services_and_falls_back_to_a_url(monkeypatch, capsys) -> None:
    services = [
        ServiceProcess(pid=10, ports=(9000,), version="1.0"),
        ServiceProcess(pid=11, cmdline=("videoflow.AppImage",)),
    ]
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(
        cli,
        "_read_pid",
        lambda path: {"pid": 10, "url": "", "host": "0.0.0.0", "port": 9000},
    )
    monkeypatch.setattr(cli, "_process_alive", lambda pid: True)
    monkeypatch.setattr(cli, "discover_services", lambda: services)
    assert cli.main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is True
    assert payload["pid"] == 10
    assert payload["url"] == "http://127.0.0.1:9000/"
    assert [item["pid"] for item in payload["services"]] == [10]


def test_status_handles_an_invalid_pid(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_pid_file", lambda: Path("/tmp/server.pid"))
    monkeypatch.setattr(cli, "_read_pid", lambda path: {"pid": None})
    monkeypatch.setattr(cli, "discover_services", lambda: [])
    assert cli.main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is False
    assert payload["pid"] is None


def test_cleanup_reports_failures(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "stop_other_services",
        lambda: {"stopped": [1], "failed": [], "services": []},
    )
    assert cli.main(["cleanup"]) == 0
    assert json.loads(capsys.readouterr().out)["failed"] == []
    monkeypatch.setattr(
        cli,
        "stop_other_services",
        lambda: {"stopped": [], "failed": [2], "services": []},
    )
    assert cli.main(["cleanup"]) == 1
    assert json.loads(capsys.readouterr().out)["failed"] == [2]


def test_restart_delegates_to_stop_and_serve(monkeypatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(cli, "_stop", lambda args: calls.setdefault("stop", args) or 0)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: calls.setdefault("sleep", seconds))

    def fake_serve(args):
        calls["serve"] = args
        return 3

    monkeypatch.setattr(cli, "_serve", fake_serve)
    assert cli.main(["restart", "--host", "0.0.0.0", "--port", "9999"]) == 3
    assert calls["sleep"] == 0.4
    assert calls["stop"].timeout == 5.0
    assert calls["serve"].host == "0.0.0.0"
    assert calls["serve"].port == 9999
    assert calls["serve"].open is True


# ---------------------------------------------------------------- doctor/mcp/main


def test_doctor_reports_missing_tools_and_writable_home(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "ensure_home", lambda: None)
    monkeypatch.setattr(cli, "find_binary", lambda _name: None)
    monkeypatch.setattr(cli, "ui_dir", lambda: tmp_path / "ui")
    monkeypatch.setattr(cli, "find_whisper_binary", lambda: None)
    monkeypatch.setattr(cli, "find_whisper_model", lambda: None)
    monkeypatch.setattr(cli, "find_faster_whisper_model", lambda size="small": None)
    monkeypatch.setattr(cli, "find_silero_model", lambda: None)
    assert cli.main(["doctor"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["home_writable"] is True
    assert payload["ffmpeg"] == {"path": None, "found": False}
    assert payload["ui"] == str(tmp_path / "ui")
    assert payload["mcp"] is True


def test_doctor_reports_write_failures_and_missing_mcp(monkeypatch, tmp_path, capsys) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")

    class Completed:
        returncode = 1
        stdout = ""
        stderr = ""

    monkeypatch.setattr(cli, "ensure_home", lambda: None)
    monkeypatch.setattr(cli, "portable_home", lambda: blocker)
    monkeypatch.setattr(cli, "find_binary", lambda _name: "/usr/bin/tool")
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: Completed())
    monkeypatch.setattr(cli, "ui_dir", lambda: None)
    monkeypatch.setattr(cli, "find_whisper_binary", lambda: None)
    monkeypatch.setattr(cli, "find_whisper_model", lambda: None)
    monkeypatch.setattr(cli, "find_faster_whisper_model", lambda size="small": None)
    monkeypatch.setattr(cli, "find_silero_model", lambda: None)
    monkeypatch.setitem(sys.modules, "mcp", None)
    assert cli.main(["doctor"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["home_writable"] is False
    assert "home_error" in payload
    assert payload["ffmpeg"]["version"] == ""
    assert payload["ffmpeg"]["exit_code"] == 1
    assert payload["whisper"]["found"] is False
    assert payload["mcp"] is False
    assert "mcp_error" in payload
    assert payload["ui"] is None


def test_mcp_runs_the_stdio_server(monkeypatch) -> None:
    modes: list[str] = []

    class FakeServer:
        def run(self, mode):
            modes.append(mode)

    monkeypatch.setattr(mcp_server_module, "build_server", lambda: FakeServer())
    assert cli.main(["mcp"]) == 0
    assert modes == ["stdio"]


def test_pid_and_browser_helpers(monkeypatch, tmp_path) -> None:
    pid_path = tmp_path / "server.pid"
    recorded: dict[str, object] = {}
    monkeypatch.setattr(cli, "service_pid_file", lambda: pid_path)
    assert cli._pid_file() == pid_path
    monkeypatch.setattr(
        cli, "write_pid_file", lambda host, port: recorded.update(host=host, port=port)
    )
    cli._write_pid(pid_path, "127.0.0.1", 8765)
    assert recorded == {"host": "127.0.0.1", "port": 8765}
    monkeypatch.setattr(cli, "read_pid_file", lambda: {"pid": 10})
    assert cli._read_pid(pid_path) == {"pid": 10}
    monkeypatch.setattr(cli, "remove_pid_file", lambda: recorded.update(removed=True))
    cli._remove_pid(pid_path)
    assert recorded["removed"] is True
    monkeypatch.setattr(cli, "process_alive", lambda pid: pid == 5)
    assert cli._process_alive(5) is True
    assert cli._process_alive(6) is False
    assert cli._browser_url("http://127.0.0.1:8765/") == (
        f"http://127.0.0.1:8765/?v={__version__}"
    )
    assert cli._browser_url("http://127.0.0.1:8765/?x=1") == (
        f"http://127.0.0.1:8765/?x=1&v={__version__}"
    )




