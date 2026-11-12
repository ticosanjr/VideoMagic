from __future__ import annotations

import json
from pathlib import Path

from videoflow.core.context import PipelineContext
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


def _context(tmp_path: Path) -> PipelineContext:
    output = tmp_path / "out"
    (output / "storyboard").mkdir(parents=True)
    (output / "storyboard" / "units.json").write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": "UNIT-0001",
                        "title": "Document",
                        "asset_query": "court document",
                        "layout": "full_screen",
                        "start_sec": 0,
                        "end_sec": 10,
                        "duration_sec": 10,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
    )


def test_discover_harvest_audit_and_assign(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    context = _context(tmp_path)
    from videoflow.application.asset_providers import AssetCandidate

    candidate = AssetCandidate(
        asset_id="wikimedia-1",
        provider="wikimedia",
        title="Court document",
        page_url="https://commons.wikimedia.org/wiki/File:doc.jpg",
        download_url="https://upload.wikimedia.org/doc.jpg",
        kind="image",
        license="CC0",
        license_status="cleared",
        allowed_commercial=True,
        attribution_required=False,
    )

    monkeypatch.setattr(
        "videoflow.steps.assets_pipeline.search_assets",
        lambda *args, **kwargs: [candidate],
    )
    AssetsDiscoverStep().run(context, DiscoverParams(max_units=1), StepIO())
    assert context.metadata["asset_candidates"][0]["unit_id"] == "UNIT-0001"

    def fake_download(candidate, destination, **kwargs):
        Path(destination).write_bytes(b"image")
        candidate.downloaded_path = str(destination)
        return candidate

    monkeypatch.setattr(
        "videoflow.steps.assets_pipeline.download_asset", fake_download
    )
    AssetsHarvestStep().run(
        context, HarvestParams(register_library=False), StepIO()
    )
    assert context.metadata["assets_manifest"]["count"] == 1
    assert (context.output / "assets" / "licenses.json").is_file()

    AssetsLicenseAuditStep().run(context, AuditParams(), StepIO())
    assert context.metadata["license_blockers"] == []

    context.metadata["gate_assets_review"] = {
        "approved": True,
        "interaction_id": "hilt-assets",
        "responded_by": "editor",
    }
    AssetsAssignStep().run(context, AssignParams(), StepIO())
    assert (context.output / "assets" / "assignments.json").is_file()
    broll = json.loads((context.output / "broll.json").read_text())
    assert broll["UNIT-0001"][0]["license_status"] == "cleared"


def test_export_blocks_unapproved_assets(tmp_path: Path) -> None:
    import pytest

    from videoflow.application.asset_providers import AssetCandidate, write_ledger
    from videoflow.domain.errors import ExportError
    from videoflow.domain.state import MediaInfo, ProjectState
    from videoflow.steps.export import ExportParams, ExportStep

    context = _context(tmp_path)
    write_ledger(
        context.output,
        [
            AssetCandidate(
                asset_id="yt-1",
                provider="youtube",
                title="Unreviewed excerpt",
                page_url="https://youtube.com/watch?v=x",
                download_url="https://youtube.com/watch?v=x",
                license="YouTube Standard License",
                license_status="fair_use_review",
            )
        ],
    )
    context.state = ProjectState(
        media_info=MediaInfo(
            source_path=str(tmp_path / "source.mp4"),
            duration_frames=100,
            fps_num=25,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        )
    )
    with pytest.raises(ExportError, match="Asset licenses"):
        ExportStep().run(context, ExportParams(require_licenses=True), StepIO())



def test_expired_asset_license_is_a_blocker(tmp_path: Path) -> None:
    from videoflow.application.asset_providers import AssetCandidate, write_ledger
    from videoflow.application.asset_providers.ledger import license_blockers

    output = tmp_path / "out"
    output.mkdir()
    write_ledger(
        output,
        [
            AssetCandidate(
                asset_id="asset-expired",
                provider="youtube",
                title="Expired clip",
                page_url="https://example.test/clip",
                download_url="https://example.test/clip.mp4",
                license="YouTube Standard",
                license_status="cleared",
                approved=True,
                expires_at="2020-01-01T00:00:00Z",
            )
        ],
    )

    blockers = license_blockers(output)
    assert [item["asset_id"] for item in blockers] == ["asset-expired"]
