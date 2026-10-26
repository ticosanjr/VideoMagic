"""Analysis cache and dubbing step: storage, pruning, providers, fallback."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.unit.test_steps_coverage_extra import make_context, make_media
from videoflow.application.settings import AppSettings
from videoflow.steps import cache as cache_module
from videoflow.steps import dubbing as dubbing_module
from videoflow.steps.base import StepIO
from videoflow.steps.cache import (
    cache_dir,
    cache_enabled,
    cache_get,
    cache_put,
    clear_cache,
    prune_cache,
)
from videoflow.steps.dubbing import DubbingParams, DubbingStep


def test_cache_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_RECIPE_CACHE", "0")
    assert cache_enabled() is False
    assert cache_get("vad", "key") is None
    assert cache_put("vad", "key", {"value": 1}) is None

    monkeypatch.setenv("VIDEOWFLOW_RECIPE_CACHE", "1")
    assert cache_enabled() is True


def test_cache_dir_uses_settings_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AppSettings()
    settings.paths.cache_dir = str(tmp_path / "custom")
    monkeypatch.setattr("videoflow.application.settings.load_settings", lambda: settings)
    assert cache_dir() == tmp_path / "custom" / "recipe-v1"

    monkeypatch.setattr(
        "videoflow.application.settings.load_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    assert cache_dir().name == "recipe-v1"


def test_cache_round_trip_and_version_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(
        "videoflow.application.settings.load_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("broken")),
    )

    path = cache_put("vad", "key", {"value": 1})

    assert path is not None
    assert cache_get("vad", "key")["value"] == 1
    assert cache_get("vad", "missing") is None

    path.write_text(json.dumps({"v": 999}), encoding="utf-8")
    assert cache_get("vad", "key") is None

    path.write_text("not json", encoding="utf-8")
    assert cache_get("vad", "key") is None


def test_cache_put_survives_disk_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(
        "videoflow.application.settings.load_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    monkeypatch.setattr(
        cache_module.os, "replace", lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk"))
    )

    assert cache_put("vad", "key", {"value": 1}) is None


def test_prune_cache_by_age_and_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(
        "videoflow.application.settings.load_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    directory = cache_dir()
    directory.mkdir(parents=True)
    old = directory / "old.json"
    new = directory / "new.json"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    ancient = time.time() - 90 * 86400
    os_utime = __import__("os").utime
    os_utime(old, (ancient, ancient))

    dry = prune_cache(max_age_days=30, dry_run=True)
    assert str(old) in dry["removed"]
    assert old.exists()

    pruned = prune_cache(max_age_days=30, max_bytes=1)
    assert str(old) in pruned["removed"]
    assert str(new) in pruned["removed"]
    assert pruned["freed_bytes"] > 0
    assert pruned["kept_bytes"] == 0

    assert prune_cache(max_age_days=30)["removed"] == []
    assert clear_cache() == 0


def test_clear_cache_removes_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(
        "videoflow.application.settings.load_settings",
        lambda: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    assert clear_cache() == 0
    cache_put("vad", "one", {"value": 1})
    cache_put("vad", "two", {"value": 2})

    assert clear_cache() == 2


def dubbing_context(tmp_path: Path):
    context = make_context(tmp_path, media_info=make_media(tmp_path))
    context.shorts = [{"title": "One"}, {"title": "Two"}]
    return context


def test_dubbing_skips_without_a_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = dubbing_context(tmp_path)
    monkeypatch.setattr(dubbing_module, "resolve_chain", lambda _capability: [])
    reports: list[str] = []

    DubbingStep().run(
        context,
        DubbingParams(),
        StepIO(progress=lambda _stage, _pct, message: reports.append(message)),
    )

    assert "no TTS provider" in reports[0]
    assert "dubbed_shorts" not in context.artifacts


def test_dubbing_uses_the_first_working_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = dubbing_context(tmp_path)
    monkeypatch.setattr(
        dubbing_module,
        "resolve_chain",
        lambda _capability: [
            {"base_url": "http://bad", "model": "bad"},
            {"base_url": "http://good", "model": "good", "voice": "v"},
        ],
    )
    monkeypatch.setattr(dubbing_module, "first_provider", lambda _capability: None)
    monkeypatch.setattr(dubbing_module, "get_secret", lambda _name: "key")
    calls: list[str] = []

    def generate(**kwargs: object) -> dict[str, object]:
        calls.append(str(kwargs["tts"].base_url))
        if kwargs["tts"].base_url == "http://bad":
            raise RuntimeError("offline")
        return {"index": kwargs["index"], "path": "dubbed.mp4"}

    monkeypatch.setattr(dubbing_module, "generate_short_dubbing", generate)

    DubbingStep().run(context, DubbingParams(), StepIO())

    assert calls == ["http://bad", "http://good", "http://bad", "http://good"]
    assert len(context.metadata["dubbed_shorts"]) == 2
    payload = json.loads(Path(context.artifacts["dubbed_shorts"]).read_text(encoding="utf-8"))
    assert payload[0]["path"] == "dubbed.mp4"


def test_dubbing_option_override_and_total_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = dubbing_context(tmp_path)
    monkeypatch.setattr(dubbing_module, "resolve_chain", lambda _capability: [])
    monkeypatch.setattr(dubbing_module, "first_provider", lambda _capability: None)
    monkeypatch.setattr(dubbing_module, "get_secret", lambda _name: "key")
    monkeypatch.setattr(
        dubbing_module,
        "generate_short_dubbing",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("tts down")),
    )

    DubbingStep().run(
        context,
        DubbingParams(base_url="http://manual", model="m", voice="v"),
        StepIO(),
    )

    assert context.metadata["dubbed_shorts"] == []
    assert any("every TTS provider" in warning for warning in context.warnings)
    assert Path(context.artifacts["dubbed_shorts"]).is_file()
