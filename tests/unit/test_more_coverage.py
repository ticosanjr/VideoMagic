from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoflow.application import search
from videoflow.application.search import SearchSettings, fetch_document, search_web
from videoflow.core.context import PipelineContext
from videoflow.steps.art_direction import (
    StoryboardUnitsStep,
    StyleGuideParams,
    StyleGuideStep,
    UnitsParams,
)
from videoflow.steps.assets_pipeline import (
    AssetsAssignStep,
    AssetsDiscoverStep,
    AssetsHarvestStep,
    AssetsLicenseAuditStep,
    AssignParams,
    AuditParams,
    DiscoverParams,
    HarvestParams,
)
from videoflow.steps.base import StepIO
from videoflow.steps.face_contact import FaceContactParams, FaceContactStep


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_style_llm_and_units_fallback(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr(
        "videoflow.steps.art_direction.palette_from_images",
        lambda *args, **kwargs: ["#111111", "#EEEEEE"],
    )
    class Llm:
        def complete_json(self, prompt: str, schema: str) -> dict:
            return {"theme": "light", "palette": ["#111111", "#EEEEEE"]}

    StyleGuideStep().run(
        context, StyleGuideParams(directive="paper"), StepIO(llm_client=Llm())
    )
    assert context.metadata["style_guide"]["theme"] == "light"

    (context.output / "research").mkdir(parents=True, exist_ok=True)
    (context.output / "research" / "master.json").write_text(
        json.dumps({"cases": [{"title": "Case", "summary": "Narration"}]}),
        encoding="utf-8",
    )
    StoryboardUnitsStep().run(context, UnitsParams(), StepIO())
    assert context.metadata["storyboard_units"][0]["title"] == "Case"


def test_face_contact_unavailable_paths(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    monkeypatch.setattr("videoflow.steps.face_contact._cv2", lambda: SimpleNamespace())
    monkeypatch.setattr("videoflow.steps.face_contact._cascades", lambda cv2: None)
    FaceContactStep().run(context, FaceContactParams(), StepIO())
    assert context.metadata["eye_contact"]["available"] is False

    context2 = PipelineContext(
        source=tmp_path / "s.mp4",
        output=tmp_path / "out2",
        work=tmp_path / "out2" / "work",
        exports=tmp_path / "out2" / "exports",
    )
    monkeypatch.setattr(
        "videoflow.steps.face_contact._cascades", lambda cv2: (SimpleNamespace(), SimpleNamespace())
    )

    class FailingAdapter:
        def extract_frames(self, *args, **kwargs):
            raise RuntimeError("no frames")

    FaceContactStep().run(
        context2, FaceContactParams(), StepIO(adapter=FailingAdapter())
    )
    assert context2.metadata["eye_contact"]["available"] is False


def test_assets_pipeline_empty_paths(tmp_path: Path) -> None:
    context = _context(tmp_path)
    AssetsDiscoverStep().run(context, DiscoverParams(), StepIO())
    assert context.metadata["asset_candidates"] == []
    AssetsHarvestStep().run(context, HarvestParams(register_library=False), StepIO())
    assert context.metadata["assets_manifest"]["count"] == 0
    AssetsLicenseAuditStep().run(context, AuditParams(), StepIO())
    AssetsAssignStep().run(context, AssignParams(), StepIO())
    assert (context.output / "assets" / "assignments.json").is_file()


def test_search_errors_and_fetch_content(monkeypatch) -> None:
    with pytest.raises(search.SearchError):
        search_web(
            "x",
            settings=SearchSettings(providers=["unknown"]),
        )
    class TextResponse:
        status_code = 200
        headers = {"content-type": "application/octet-stream"}
        content = b"binary"
        encoding = "utf-8"

    monkeypatch.setattr(search.httpx, "get", lambda *args, **kwargs: TextResponse())
    monkeypatch.setattr(search, "_assert_public_url", lambda *args, **kwargs: None)
    monkeypatch.setattr(search, "_robots_allowed", lambda *args, **kwargs: True)
    with pytest.raises(search.SearchError):
        fetch_document(
            "https://example.com/file.bin",
            SearchSettings(),
            allow_external_services=True,
        )
