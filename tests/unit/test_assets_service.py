from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.asset_providers.ledger import license_blockers
from videoflow.application.assets_service import asset_records, review_assets
from videoflow.domain.state import MediaInfo, OverlayClip, ProjectState


def _project(tmp_path: Path) -> tuple[Path, ProjectState, Path, Path]:
    output = tmp_path / "out"
    (output / "assets").mkdir(parents=True)
    used = output / "assets" / "used.png"
    unused = output / "assets" / "unused.png"
    used.write_bytes(b"used")
    unused.write_bytes(b"unused")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=48000,
    )
    state = ProjectState(
        media_info=media,
        overlays=[
            OverlayClip(
                overlay_id="used",
                path=str(used),
                start_frame=0,
                duration_frames=30,
            )
        ],
    )
    (output / "assets" / "licenses.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_id": "used",
                        "title": str(used),
                        "path": str(used),
                        "license": "unknown",
                        "license_status": "unknown",
                    },
                    {
                        "asset_id": "unused",
                        "title": str(unused),
                        "path": str(unused),
                        "license": "unknown",
                        "license_status": "unknown",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return output, state, used, unused


def test_license_blockers_are_scoped_to_timeline_assets(tmp_path: Path) -> None:
    output, state, used, unused = _project(tmp_path)
    blockers = license_blockers(output, state)
    titles = {str(item["title"]) for item in blockers}
    assert str(used) in titles
    assert str(unused) not in titles


def test_workspace_blockers_are_scoped_to_timeline_assets(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    import vf_contracts.workspace as workspace
    from vf_contracts.assets import write_asset

    monkeypatch.setenv("VF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    output = tmp_path / "out"
    output.mkdir()
    (output / "project.json").write_text(
        json.dumps({"project_id": "scope-proj"}),
        encoding="utf-8",
    )
    used = write_asset("scope-proj", "broll", b"used", {"license": "unknown"})
    unused = write_asset("scope-proj", "broll", b"unused", {"license": "unknown"})
    source = workspace.project_dir("scope-proj") / used.path
    state = SimpleNamespace(
        media_info=SimpleNamespace(source_path=str(source)),
        sources={},
        overlays=[],
        video_segments=[],
        audio_segments=[],
    )
    titles = {str(item["title"]) for item in license_blockers(output, state)}
    assert used.path in titles
    assert unused.path not in titles
    assert {str(item["title"]) for item in license_blockers(output)} >= {
        used.path,
        unused.path,
    }


def test_asset_list_and_approve_and_quarantine(tmp_path: Path) -> None:
    output, state, used, unused = _project(tmp_path)
    records = asset_records(output, state=state)
    assert {item["asset_id"] for item in records} == {"used", "unused"}
    assert next(item for item in records if item["asset_id"] == "used")["referenced"] is True

    approved = review_assets(
        output,
        action="approve",
        asset_ids=["used"],
        license="cc-by",
        attribution="Author",
    )
    assert approved["ok"] is True
    assert license_blockers(output, state) == []
    quarantined = review_assets(
        output,
        action="quarantine",
        asset_ids=["unused"],
        reason="unclear",
    )
    assert quarantined["ok"] is True
    assert any(
        item["asset_id"] == "unused" for item in asset_records(output, state=state)
    )


def test_asset_records_merges_workspace_and_skips_bad_entries(
    tmp_path: Path, monkeypatch
) -> None:
    from videoflow.application import assets_service as service

    output, state, _used, _unused = _project(tmp_path)
    (output / "assets" / "licenses.json").unlink()
    monkeypatch.setattr(
        service,
        "_workspace_records",
        lambda project_id: [
            "bad",
            {"asset_id": "ws-1", "path": "assets/used.png", "license_status": "clear"},
            {"asset_id": "ws-1", "title": "duplicate"},
            {"path": "", "id": ""},
        ],
    )
    records = asset_records(output, project_id="p", state=state)
    assert [item["asset_id"] for item in records] == ["ws-1"]
    assert records[0]["referenced"] is True
    assert records[0]["source"] == "workspace"


def test_approve_workspace_only_asset_persists_ledger(
    tmp_path: Path, monkeypatch
) -> None:
    from videoflow.application import assets_service as service

    output, _state, _used, _unused = _project(tmp_path)
    (output / "assets" / "licenses.json").unlink()
    monkeypatch.setattr(
        service,
        "_workspace_records",
        lambda project_id: [
            {"asset_id": "ws-1", "path": "assets/used.png", "license": "cc0"}
        ],
    )
    result = review_assets(
        output,
        action="approve",
        project_id="p",
        asset_ids=["ws-1"],
        attribution="Author",
    )
    assert result["changed"] == ["ws-1"]
    payload = json.loads((output / "assets" / "licenses.json").read_text(encoding="utf-8"))
    assert payload["assets"][0]["license_status"] == "clear"
    assert payload["assets"][0]["attribution"] == "Author"
    assert payload["blockers"] == []


def test_review_assets_requires_ids_and_reports_unknown(tmp_path: Path) -> None:
    import pytest

    from videoflow.domain.errors import AssetNotFoundError

    output, _state, _used, _unused = _project(tmp_path)
    with pytest.raises(AssetNotFoundError):
        review_assets(output, action="approve")
    with pytest.raises(AssetNotFoundError):
        review_assets(output, action="quarantine", asset_ids=["missing"])


def test_asset_records_tolerates_bad_ledger_and_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    import pytest
    import vf_contracts.assets as contract_assets

    from videoflow.application import assets_service as service
    from videoflow.domain.errors import AssetNotFoundError

    output = tmp_path / "out"
    output.mkdir()

    def explode(project_id):
        raise RuntimeError("workspace index unavailable")

    monkeypatch.setattr(contract_assets, "iter_assets", explode)
    monkeypatch.setattr(service, "read_ledger", lambda root: {"assets": {}})
    assert asset_records(output, project_id="p") == []
    with pytest.raises(AssetNotFoundError):
        review_assets(output, action="approve", asset_ids=["x"])


def test_vf_assets_tool_lists_approves_and_quarantines(tmp_path: Path) -> None:
    from videoflow.application.jobs import JobManager
    from videoflow.application.projects import init_project
    from videoflow.mcp_server.context import ToolContext
    from videoflow.mcp_server.core_tools import register_core_tools

    record, _state = init_project(
        project_id="assets-tool",
        name="Assets",
        output=tmp_path / "assets-tool",
    )
    ledger = Path(record.output) / "assets" / "licenses.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_id": "clip",
                        "title": "Clip",
                        "path": "assets/clip.mp4",
                        "license": "unknown",
                        "license_status": "unknown",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manager = JobManager(store_dir=tmp_path / "jobs", load_store=False)
    tools: dict[str, object] = {}
    register_core_tools(
        lambda func: tools.setdefault(func.__name__, func),
        ToolContext(manager=manager),
    )

    missing = tools["vf_assets"]()
    assert missing["ok"] is False
    assert tools["vf_assets"](action="bogus", project_id=record.project_id)["ok"] is False
    listed = tools["vf_assets"](project_id=record.project_id)
    assert listed["count"] == 1
    missing_asset = tools["vf_assets"](
        action="approve",
        project_id=record.project_id,
        asset_ids=["nope"],
    )
    assert missing_asset["ok"] is False
    approved = tools["vf_assets"](
        action="approve",
        project_id=record.project_id,
        asset_ids=["clip"],
        license="cc-by",
        attribution="Author",
    )
    assert approved["ok"] is True
    assert approved["assets"][0]["blocked"] is False
    quarantined = tools["vf_assets"](
        action="quarantine",
        project_id=record.project_id,
        asset_ids=["clip"],
        reason="unclear",
    )
    assert quarantined["ok"] is True
    assert quarantined["assets"][0]["blocked"] is True
