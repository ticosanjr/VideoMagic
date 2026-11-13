from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.asset_providers.models import AssetCandidate
from videoflow.core.context import PipelineContext
from videoflow.steps import assets_pipeline
from videoflow.steps.assets_pipeline import (
    AssetsAssignStep,
    AssetsDiscoverStep,
    AssetsHarvestStep,
    AssetsLicenseAuditStep,
    AssignParams,
    DiscoverParams,
    HarvestParams,
)
from videoflow.steps.base import StepIO


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    output.mkdir(parents=True)
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_discover_fallback_and_errors(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    context.metadata["narrative_beats"] = [
        "bad",
        {"context_block_id": "b1", "text": "court document"},
    ]
    calls: list[str] = []

    def fake_search(query, **kwargs):
        calls.append(query)
        if "fail" in query:
            raise RuntimeError("provider down")
        return [
            AssetCandidate(
                asset_id="a1",
                provider="wikimedia",
                title="Doc",
                page_url="https://x/1",
                download_url="https://x/1.jpg",
                kind="image",
            )
        ]

    monkeypatch.setattr(assets_pipeline, "search_assets", fake_search)
    AssetsDiscoverStep().run(
        context,
        DiscoverParams(providers=["wikimedia"]),
        StepIO(),
    )
    payload = json.loads((context.output / "assets" / "candidates.json").read_text())
    assert payload["count"] == 1
    assert calls == ["court document"]
    assert AssetsDiscoverStep().cache_outputs(context)

    (context.output / "storyboard").mkdir(parents=True)
    (context.output / "storyboard" / "units.json").write_text(
        json.dumps(
            {
                "units": [
                    1,
                    {"unit_id": "U1", "asset_query": ""},
                    {"unit_id": "U2", "asset_query": "fail"},
                ]
            }
        )
    )
    AssetsDiscoverStep().run(context, DiscoverParams(), StepIO())
    payload = json.loads((context.output / "assets" / "candidates.json").read_text())
    assert payload["warnings"]
    assert AssetsDiscoverStep().cache_outputs(_context(tmp_path / "empty")) == ()


def test_suffix_variants_and_harvest_edges(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    (context.output / "assets").mkdir(parents=True, exist_ok=True)
    (context.output / "assets" / "candidates.json").write_text(
        json.dumps(
            {
                "candidates": [
                    1,
                    {
                        "asset_id": "video",
                        "provider": "x",
                        "title": "V",
                        "page_url": "",
                        "download_url": "https://x/v.mp4",
                    },
                    {
                        "asset_id": "image",
                        "provider": "x",
                        "title": "I",
                        "page_url": "",
                        "download_url": "https://x/i.jpg",
                    },
                    {
                        "asset_id": "audio",
                        "provider": "x",
                        "title": "A",
                        "page_url": "",
                        "download_url": "https://x/a.mp3",
                    },
                    {
                        "asset_id": "unknown",
                        "provider": "x",
                        "title": "U",
                        "page_url": "",
                        "download_url": "https://x/u",
                    },
                ]
            }
        )
    )
    assert assets_pipeline._suffix(
        AssetCandidate("v", "x", "V", "", "https://x/v.mov")
    ) == ".mov"
    assert assets_pipeline._suffix(
        AssetCandidate("i", "x", "I", "", "https://x/i.png")
    ) == ".png"
    assert assets_pipeline._suffix(
        AssetCandidate("a", "x", "A", "", "https://x/a.wav")
    ) == ".wav"
    assert assets_pipeline._suffix(
        AssetCandidate("u", "x", "U", "", "https://x/u", kind="video")
    ) == ".mp4"
    assert assets_pipeline._suffix(
        AssetCandidate("u", "x", "U", "", "https://x/u", kind="image")
    ) == ".jpg"
    assert assets_pipeline._suffix(
        AssetCandidate("u", "x", "U", "", "https://x/u", kind="audio")
    ) == ".bin"

    downloaded: list[Path] = []
    scanned: list[Path] = []

    def fake_download(candidate, target, **kwargs):
        if candidate.asset_id == "image":
            raise RuntimeError("download failed")
        Path(target).write_bytes(b"data")
        downloaded.append(Path(target))
        return candidate

    monkeypatch.setattr(assets_pipeline, "download_asset", fake_download)
    monkeypatch.setattr(
        assets_pipeline, "scan_directory", lambda path, **kwargs: scanned.append(path)
    )
    AssetsHarvestStep().run(context, HarvestParams(register_library=True), StepIO())
    manifest = json.loads((context.output / "assets" / "manifest.json").read_text())
    assert manifest["count"] == 3
    assert manifest["warnings"]
    assert scanned
    assert AssetsHarvestStep().cache_outputs(context)

    (context.output / "assets" / "candidates.json").write_text('{"candidates": 3}')
    AssetsHarvestStep().run(context, HarvestParams(), StepIO())
    manifest = json.loads((context.output / "assets" / "manifest.json").read_text())
    assert manifest["count"] == 0


def test_audit_and_assign_edges(tmp_path: Path, monkeypatch) -> None:
    context = _context(tmp_path)
    AssetsLicenseAuditStep().run(context, AssetsLicenseAuditStep.params_model(), StepIO())
    assert context.metadata["license_blockers"] == []
    assert AssetsLicenseAuditStep().cache_outputs(context)

    (context.output / "assets").mkdir(parents=True, exist_ok=True)
    (context.output / "assets" / "manifest.json").write_text(
        json.dumps(
            {
                "assets": [
                    1,
                    {
                        "asset_id": "a",
                        "unit_id": "U1",
                        "downloaded_path": "/a.jpg",
                        "kind": "image",
                    },
                    {
                        "asset_id": "b",
                        "unit_id": "U1",
                        "downloaded_path": "",
                        "kind": "image",
                    },
                    {
                        "asset_id": "c",
                        "unit_id": "U2",
                        "downloaded_path": "/c.bin",
                        "kind": "audio",
                    },
                ]
            }
        )
    )
    (context.output / "storyboard").mkdir(exist_ok=True)
    (context.output / "storyboard" / "units.json").write_text(
        json.dumps(
            {
                "units": [
                    1,
                    {"unit_id": "U1", "layout": "full_screen", "start_sec": 1, "duration_sec": 4},
                    {"unit_id": "U2", "layout": "full_screen"},
                ]
            }
        )
    )
    approvals: list[str] = []
    monkeypatch.setattr(
        assets_pipeline,
        "mark_approved",
        lambda output, **kwargs: approvals.append(kwargs["approval_id"]),
    )
    context.metadata["gate_assets_review"] = {
        "approved": True,
        "interaction_id": "gate-1",
        "responded_by": "human",
    }
    AssetsAssignStep().run(context, AssignParams(), StepIO())
    assert approvals == ["gate-1"]
    assignments = json.loads(
        (context.output / "assets" / "assignments.json").read_text()
    )["assignments"]
    assert assignments[0]["cue"]["duration_sec"] == 4
    assert assignments[1]["asset"] is None
    assert AssetsAssignStep().cache_outputs(context)
