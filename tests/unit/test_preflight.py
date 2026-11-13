from __future__ import annotations

from pathlib import Path

from videoflow.application import preflight
from videoflow.application.preflight import preflight_recipe
from videoflow.core.recipe import parse_recipe


def _recipe(*steps: dict) -> object:
    return parse_recipe(
        {
            "schema_version": 1,
            "id": "preflight_recipe",
            "name": "Preflight",
            "steps": list(steps),
        }
    )


def _ingest() -> dict:
    return {"id": "ingest", "type": "ingest", "needs": []}


def _ok_runtime(monkeypatch, tmp_path: Path | None = None) -> None:
    if tmp_path is not None:
        monkeypatch.setattr(preflight, "allowed_roots", lambda: [tmp_path])
    monkeypatch.setattr(preflight, "_provider_items", lambda: [])
    monkeypatch.setattr(
        preflight, "find_binary", lambda name: f"/usr/bin/{name}"
    )
    monkeypatch.setattr(preflight, "find_whisper_binary", lambda: "/usr/bin/whisper")
    monkeypatch.setattr(preflight, "find_whisper_model", lambda: Path("/models/whisper.bin"))


def test_preflight_blocks_missing_source(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    report = preflight_recipe(
        _recipe(_ingest()), source="", output=str(tmp_path / "out")
    )
    assert report.ready is False
    check = next(item for item in report.checks if item.id == "input.source")
    assert check.status == "error"


def test_preflight_accepts_a_ready_ingest(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    report = preflight_recipe(
        _recipe(_ingest()), source=str(source), output=str(tmp_path / "out")
    )
    assert report.ready is True, report.to_dict()
    assert report.errors == 0


def test_preflight_reports_missing_ffmpeg(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(preflight, "find_binary", lambda name: None)
    report = preflight_recipe(
        _recipe(_ingest()), source=str(source), output=str(tmp_path / "out")
    )
    assert report.ready is False
    assert any(
        item.id == "runtime.ffmpeg" and item.status == "error"
        for item in report.checks
    )


def test_preflight_reports_missing_required_variables(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "vars",
            "name": "Vars",
            "variables": {"topic": {"type": "string", "required": True}},
            "steps": [{"id": "ingest", "type": "ingest", "needs": []}],
        }
    )
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    report = preflight_recipe(
        recipe, source=str(source), output=str(tmp_path / "out")
    )
    assert report.ready is False
    assert any(item.id == "input.variables" for item in report.checks)


def test_preflight_warns_about_optional_backends(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(preflight, "_module_available", lambda name: False)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    recipe = _recipe(
        _ingest(),
        {"id": "ocr", "type": "vision.ocr", "needs": ["ingest"]},
    )
    report = preflight_recipe(
        recipe, source=str(source), output=str(tmp_path / "out")
    )
    check = next(item for item in report.checks if item.id == "optional.ocr")
    assert check.status == "warning"


def test_preflight_reports_explicit_provider_errors(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(
        preflight,
        "_provider_items",
        lambda: [
            {
                "id": "voice",
                "name": "Voice",
                "capability": "tts",
                "configured": False,
                "api_key_env": "",
            }
        ],
    )
    recipe = _recipe(
        {
            "id": "voice",
            "type": "narration.synthesize",
            "needs": [],
            "params": {"provider_id": "missing"},
        }
    )
    report = preflight_recipe(
        recipe, output=str(tmp_path / "out"), variables={}
    )
    check = next(item for item in report.checks if item.id == "provider.tts")
    assert check.status == "error"


def test_writable_target_checks_the_existing_parent(tmp_path: Path) -> None:
    ok, _ = preflight._writable_target(tmp_path / "new" / "nested")
    assert ok is True
    missing, reason = preflight._writable_target(Path("/root/forbidden/out"))
    assert missing is False
    assert reason


def test_preflight_helper_guards(monkeypatch, tmp_path: Path) -> None:
    import importlib.util


    def boom(*args, **kwargs):
        raise ValueError("bad spec")

    monkeypatch.setattr(importlib.util, "find_spec", boom)
    assert preflight._module_available("missing") is False

    monkeypatch.setattr(
        preflight, "list_providers", lambda: (_ for _ in ()).throw(RuntimeError("db"))
    )
    assert preflight._provider_items() == []
    assert preflight._has_secret({"api_key_env": ""}) is True
    monkeypatch.setattr(preflight, "get_secret", lambda name: "")
    assert preflight._has_secret({"api_key_env": "MISSING"}) is False

    original_exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda self: False)
    ok, reason = preflight._writable_target(tmp_path / "a" / "b")
    assert ok is False
    assert reason
    monkeypatch.setattr(Path, "exists", original_exists)
    monkeypatch.setattr(preflight.os, "access", lambda path, mode: False)
    ok, reason = preflight._writable_target(tmp_path)
    assert ok is False
    assert "not writable" in reason


def test_preflight_reports_graph_and_port_errors(tmp_path: Path, monkeypatch) -> None:
    from videoflow.domain.errors import RecipeError

    _ok_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    broken = _recipe(
        {"id": "a", "type": "ingest", "needs": ["missing"]},
    )
    report = preflight_recipe(broken, source=str(source), output=str(tmp_path / "out"))
    assert any(item.id == "recipe.graph" and item.status == "error" for item in report.checks)

    recipe = _recipe(_ingest())
    monkeypatch.setattr(
        preflight,
        "validate_recipe_ports",
        lambda *args, **kwargs: (_ for _ in ()).throw(RecipeError("bad ports")),
    )
    report = preflight_recipe(recipe, source=str(source), output=str(tmp_path / "out"))
    assert any(item.id == "recipe.ports" and item.status == "error" for item in report.checks)


def test_preflight_rejects_bad_paths(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    report = preflight_recipe(
        _recipe(_ingest()), source="/etc/passwd", output=str(tmp_path / "out")
    )
    assert any(item.id == "input.source" and item.status == "error" for item in report.checks)
    report = preflight_recipe(
        _recipe(_ingest()), source=str(tmp_path / "missing.mp4"), output="/etc"
    )
    assert any(item.id == "input.source" and item.status == "error" for item in report.checks)
    assert any(item.id == "input.output" and item.status == "error" for item in report.checks)


def test_preflight_validates_step_params(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    report = preflight_recipe(
        _recipe(
            _ingest(),
            {
                "id": "ocr",
                "type": "vision.ocr",
                "needs": ["ingest"],
                "params": {"max_frames": 0},
            },
        ),
        source=str(source),
        output=str(tmp_path / "out"),
    )
    assert any(
        item.id == "recipe.params.ocr" and item.status == "error"
        for item in report.checks
    )


def test_preflight_transcription_modes(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    recipe = _recipe(
        _ingest(),
        {"id": "transcribe", "type": "transcribe", "needs": ["ingest"], "params": {"mode": "srt"}},
    )
    report = preflight_recipe(recipe, source=str(source), output=str(tmp_path / "out"))
    assert next(item for item in report.checks if item.id == "runtime.transcribe").status == "ok"

    for mode in ("whisper_cpp", "http", "auto"):
        monkeypatch.setattr(preflight, "_module_available", lambda name: False)
        monkeypatch.setattr(preflight, "find_whisper_binary", lambda: None)
        monkeypatch.setattr(preflight, "find_whisper_model", lambda: None)
        recipe = _recipe(
            _ingest(),
            {
                "id": "transcribe",
                "type": "transcribe",
                "needs": ["ingest"],
                "params": {"mode": mode},
            },
        )
        report = preflight_recipe(
            recipe, source=str(source), output=str(tmp_path / "out")
        )
        assert next(
            item for item in report.checks if item.id == "runtime.transcribe"
        ).status == "warning"


def test_preflight_optional_backends_and_providers(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(preflight, "_module_available", lambda name: False)
    monkeypatch.setattr(preflight, "find_binary", lambda name: None)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    recipe = _recipe(
        _ingest(),
        {"id": "scene_code", "type": "scene.codegen", "needs": []},
        {
            "id": "scene",
            "type": "scene.render",
            "needs": ["scene_code"],
            "params": {"engine": "playwright"},
        },
        {"id": "face", "type": "vision.face_contact", "needs": ["ingest"]},
        {"id": "isolate", "type": "audio.isolate", "needs": ["ingest"]},
        {
            "id": "harvest",
            "type": "assets.harvest",
            "needs": [],
            "params": {"providers": ["youtube"]},
        },
        {
            "id": "voice",
            "type": "narration.synthesize",
            "needs": [],
            "params": {"provider_id": "voice"},
        },
    )
    monkeypatch.setattr(
        preflight,
        "_provider_items",
        lambda: [
            {
                "id": "voice",
                "name": "Voice",
                "capability": "tts",
                "configured": True,
                "api_key_env": "MISSING",
            }
        ],
    )
    monkeypatch.setattr(preflight, "get_secret", lambda name: "")
    report = preflight_recipe(recipe, source=str(source), output=str(tmp_path / "out"))
    ids = {item.id for item in report.checks}
    assert "optional.playwright" in ids
    assert "optional.vision" in ids
    assert "optional.isolation" in ids
    assert "optional.youtube" in ids
    assert any(item.id == "provider.tts" and item.status == "warning" for item in report.checks)


def test_preflight_disk_thresholds(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    _ok_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    recipe = _recipe(_ingest())
    monkeypatch.setattr(
        preflight.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=50 * 1024 * 1024, total=100 * 1024 * 1024),
    )
    report = preflight_recipe(recipe, source=str(source), output=str(tmp_path / "out"))
    assert any(item.id == "runtime.disk" and item.status == "error" for item in report.checks)
    monkeypatch.setattr(
        preflight.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(free=500 * 1024 * 1024, total=100 * 1024 * 1024),
    )
    report = preflight_recipe(recipe, source=str(source), output=str(tmp_path / "out"))
    assert any(item.id == "runtime.disk" and item.status == "warning" for item in report.checks)


def test_preflight_report_and_param_videoflow_errors(tmp_path: Path, monkeypatch) -> None:
    from videoflow.domain.errors import RecipeError

    check = preflight.PreflightCheck("x", "recipe", "ok", "X")
    assert check.to_dict()["id"] == "x"
    report = preflight.PreflightReport([])
    assert report.to_dict()["ready"] is True
    report = preflight.PreflightReport(
        [preflight.PreflightCheck("x", "recipe", "warning", "X")]
    )
    assert report.to_dict()["warnings"] == 1

    _ok_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    recipe = _recipe(_ingest(), {"id": "bad", "type": "vision.ocr", "needs": ["ingest"]})

    class BadStep:
        def validate_params(self, params):
            raise RecipeError("bad params")

    monkeypatch.setattr(preflight, "get_step", lambda step_type: BadStep())
    report = preflight_recipe(recipe, source=str(source), output=str(tmp_path / "out"))
    assert any(
        item.id == "recipe.params.bad" and item.status == "error"
        for item in report.checks
    )


def test_preflight_optional_variables_report_ok(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "optional_vars",
            "name": "Optional vars",
            "variables": {"topic": {"type": "string", "required": False}},
            "steps": [{"id": "ingest", "type": "ingest", "needs": []}],
        }
    )
    report = preflight_recipe(
        recipe,
        source=str(source),
        output=str(tmp_path / "out"),
        variables={"topic": "x"},
    )
    assert any(item.id == "input.variables" and item.status == "ok" for item in report.checks)


def test_preflight_scene_alignment_and_broll_checks(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(preflight, "find_binary", lambda name: f"/usr/bin/{name}")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    scene = _recipe(
        {"id": "code", "type": "scene.codegen", "needs": []},
        {
            "id": "scene",
            "type": "scene.render",
            "needs": ["code"],
            "params": {"engine": "playwright"},
        },
    )
    monkeypatch.setattr(preflight, "_module_available", lambda name: True)
    report = preflight_recipe(scene, source=str(source), output=str(tmp_path / "out"))
    assert any(
        item.id == "optional.playwright" and item.status == "ok"
        for item in report.checks
    )

    aligned = _recipe(
        _ingest(),
        {
            "id": "transcribe",
            "type": "transcribe",
            "needs": ["ingest"],
            "params": {"mode": "srt"},
        },
        {
            "id": "align",
            "type": "alignment.forced",
            "needs": ["transcribe"],
        },
    )
    monkeypatch.setattr(
        preflight,
        "_module_available",
        lambda name: name in {"whisperx", "faster_whisper"},
    )
    report = preflight_recipe(
        aligned, source=str(source), output=str(tmp_path / "out")
    )
    assert any(
        item.id == "optional.alignment" and item.status == "ok"
        for item in report.checks
    )

    broll = _recipe(
        _ingest(),
        {
            "id": "transcribe",
            "type": "transcribe",
            "needs": ["ingest"],
            "params": {"mode": "srt"},
        },
        {"id": "shorts", "type": "shorts.select", "needs": ["transcribe"]},
        {
            "id": "broll",
            "type": "broll.generate",
            "needs": ["shorts"],
            "params": {"base_url": "", "api_key_env": "MISSING"},
        },
    )
    monkeypatch.setattr(preflight, "get_secret", lambda name: "")
    report = preflight_recipe(broll, source=str(source), output=str(tmp_path / "out"))
    image = next(item for item in report.checks if item.id == "optional.image")
    assert image.status == "warning"

    monkeypatch.setattr(preflight, "get_secret", lambda name: "secret")
    report = preflight_recipe(broll, source=str(source), output=str(tmp_path / "out"))
    assert next(
        item for item in report.checks if item.id == "optional.image"
    ).status == "warning"


def test_preflight_provider_ready_and_missing(tmp_path: Path, monkeypatch) -> None:
    _ok_runtime(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    recipe = _recipe(
        {
            "id": "voice",
            "type": "narration.synthesize",
            "needs": [],
            "params": {},
        }
    )
    monkeypatch.setattr(
        preflight,
        "_provider_items",
        lambda: [
            {
                "id": "voice",
                "name": "Voice",
                "capability": "tts",
                "configured": True,
                "api_key_env": "",
            }
        ],
    )
    report = preflight_recipe(recipe, output=str(tmp_path / "out"))
    assert any(
        item.id == "provider.tts" and item.status == "ok" for item in report.checks
    )
    monkeypatch.setattr(preflight, "_provider_items", lambda: [])
    report = preflight_recipe(recipe, output=str(tmp_path / "out"))
    assert any(
        item.id == "provider.tts" and item.status == "warning"
        for item in report.checks
    )
