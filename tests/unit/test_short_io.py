from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application.scene_intel.io import write_json
from videoflow.application.short_composition.io import (
    read_cues,
    read_export_report,
    read_manifest,
    read_optional_plan,
    read_plan,
)
from videoflow.domain.errors import ShortPlanError, StateNotReadyError


def _plan() -> dict:
    return {
        "short_id": "SH_001",
        "start": 0.0,
        "end": 4.0,
        "segments": [
            {
                "seg_id": "SEG_01",
                "layout": "FULL_FACE",
                "rel_start": 0.0,
                "rel_end": 4.0,
            }
        ],
    }


def _context(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(metadata={}, artifacts={})


def test_plan_precedence_override_then_metadata_then_artifact(tmp_path: Path) -> None:
    context = _context(tmp_path)
    artifact = tmp_path / "plan.json"
    write_json(artifact, _plan())
    context.artifacts["short_plan"] = str(artifact)
    assert read_plan(context, step="short.render").short_id == "SH_001"

    context.metadata["short_plan"] = {**_plan(), "short_id": "SH_META"}
    assert read_plan(context, step="short.render").short_id == "SH_META"

    override = tmp_path / "override.json"
    write_json(override, {**_plan(), "short_id": "SH_OVERRIDE"})
    assert read_optional_plan(context, str(override))["short_id"] == "SH_OVERRIDE"
    assert read_plan(context, str(override), step="short.render").short_id == "SH_OVERRIDE"


def test_plan_missing_and_invalid_errors(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(StateNotReadyError):
        read_plan(context, step="short.render")
    context.metadata["short_plan"] = {"short_id": "bad id", "start": 0, "end": 1}
    with pytest.raises(ShortPlanError):
        read_plan(context, step="short.render")


def test_manifest_and_cues_fallbacks(tmp_path: Path) -> None:
    context = _context(tmp_path)
    manifest = {
        "video_id": "v",
        "resolution": {"w": 1920, "h": 1080},
        "fps_num": 30,
        "fps_den": 1,
        "scenes": [],
    }
    context.metadata["scenes_manifest"] = manifest
    assert read_manifest(context, step="short.render").video_id == "v"

    cues = {"sfx": [{"asset": "whoosh.wav", "time_sec": 1.0}]}
    context.metadata["short_cues"] = cues
    assert read_cues(context)["sfx"][0]["asset"] == "whoosh.wav"

    report = {"ok": True}
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    context.artifacts["short_export_report"] = str(report_path)
    assert read_export_report(context)["ok"] is True


def test_invalid_manifest_uses_caller_error_type(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.metadata["scenes_manifest"] = {"video_id": "v"}
    with pytest.raises(ShortPlanError):
        read_manifest(context, step="short.render")
