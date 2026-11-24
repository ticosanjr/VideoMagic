"""Unified style + workflow catalog bundle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.application.catalog_bundle import (
    InvalidCatalogBundleError,
    export_catalog_bundle,
    import_catalog_bundle,
)
from videoflow.application.style_catalog import StyleCatalog, render_style_markdown
from videoflow.application.workflow_catalog import (
    WorkflowCatalog,
    render_workflow_markdown,
)
from videoflow.domain.styles import StyleDefinition
from videoflow.domain.workflows import WorkflowDefinition


def _style(identifier: str, *, body: str = "# Direção\n\nCorpo do estilo.\n") -> str:
    return render_style_markdown(
        StyleDefinition(style_id=identifier, name=identifier.title(), body=body)
    )


def _workflow(identifier: str, *, body: str = "# Fluxo\n\nCorpo do workflow.\n") -> str:
    return render_workflow_markdown(
        WorkflowDefinition(workflow_id=identifier, name=identifier.title(), body=body)
    )


def _catalogs(tmp_path: Path) -> tuple[StyleCatalog, WorkflowCatalog]:
    return (
        StyleCatalog(tmp_path / "styles", include_seeds=False),
        WorkflowCatalog(tmp_path / "workflows", include_seeds=False),
    )


def test_export_import_round_trip_keeps_markdown(tmp_path: Path) -> None:
    styles, workflows = _catalogs(tmp_path)
    styles.save(StyleDefinition(style_id="alpha", name="Alpha", body="# Alpha\n"))
    workflows.save(
        WorkflowDefinition(workflow_id="flow-a", name="Flow A", body="# Flow\n")
    )
    style_text = (tmp_path / "styles" / "alpha.md").read_text(encoding="utf-8")
    workflow_text = (tmp_path / "workflows" / "flow-a.md").read_text(encoding="utf-8")

    bundle = export_catalog_bundle(
        style_catalog=styles,
        workflow_catalog=workflows,
    )
    assert bundle.styles[0].markdown_content == style_text
    assert bundle.workflows[0].markdown_content == workflow_text

    style_file = tmp_path / "styles" / "alpha.md"
    workflow_file = tmp_path / "workflows" / "flow-a.md"
    style_file.unlink()
    workflow_file.unlink()
    result = import_catalog_bundle(
        bundle.model_dump(mode="json"),
        style_catalog=styles,
        workflow_catalog=workflows,
    )
    assert result == {
        "ok": True,
        "imported_styles": 1,
        "skipped_styles": 0,
        "imported_workflows": 1,
        "skipped_workflows": 0,
        "synced": False,
    }
    assert style_file.read_text(encoding="utf-8") == style_text
    restored = workflows.get("flow-a")
    assert restored.name == "Flow A"
    assert restored.body.strip() == "# Flow"


def test_import_without_overwrite_skips_existing_items(tmp_path: Path) -> None:
    styles, workflows = _catalogs(tmp_path)
    styles.save(StyleDefinition(style_id="alpha", name="Alpha", body="# Old\n"))
    bundle = {
        "schema_version": 1,
        "styles": [
            {"id": "alpha", "markdown_content": _style("alpha", body="# New\n")},
            {"id": "beta", "markdown_content": _style("beta", body="# Beta\n")},
        ],
        "workflows": [],
    }
    result = import_catalog_bundle(
        bundle,
        overwrite=False,
        style_catalog=styles,
        workflow_catalog=workflows,
    )
    assert result["imported_styles"] == 1
    assert result["skipped_styles"] == 1
    assert styles.get("alpha").body.strip() == "# Old"
    assert (tmp_path / "styles" / "beta.md").is_file()


def test_path_traversal_is_rejected_before_any_write(tmp_path: Path) -> None:
    styles, workflows = _catalogs(tmp_path)
    bundle = {
        "schema_version": 1,
        "styles": [
            {"id": "safe", "markdown_content": _style("safe")},
            {"id": "../evil", "markdown_content": _style("safe")},
        ],
        "workflows": [],
    }
    with pytest.raises(InvalidCatalogBundleError) as error:
        import_catalog_bundle(
            bundle,
            style_catalog=styles,
            workflow_catalog=workflows,
        )
    assert "invalid bundle" in str(error.value)
    assert not list((tmp_path / "styles").glob("*.md"))


def test_one_corrupt_workflow_blocks_every_style(tmp_path: Path) -> None:
    styles, workflows = _catalogs(tmp_path)
    bundle = {
        "schema_version": 1,
        "styles": [
            {"id": f"style-{index}", "markdown_content": _style(f"style-{index}")}
            for index in range(3)
        ],
        "workflows": [
            {"id": "broken", "markdown_content": "not markdown"},
        ],
    }
    with pytest.raises(InvalidCatalogBundleError) as error:
        import_catalog_bundle(
            bundle,
            style_catalog=styles,
            workflow_catalog=workflows,
        )
    assert "invalid workflow 'broken'" in str(error.value)
    assert not list((tmp_path / "styles").glob("*.md"))
    assert not list((tmp_path / "workflows").glob("*.md"))


def test_empty_bundle_is_rejected(tmp_path: Path) -> None:
    styles, workflows = _catalogs(tmp_path)
    with pytest.raises(InvalidCatalogBundleError) as error:
        import_catalog_bundle(
            {"schema_version": 1, "styles": [], "workflows": []},
            style_catalog=styles,
            workflow_catalog=workflows,
        )
    assert "no styles or workflows" in str(error.value)


def test_bom_json_is_accepted(tmp_path: Path) -> None:
    styles, workflows = _catalogs(tmp_path)
    payload = {
        "schema_version": 1,
        "styles": [{"id": "bom-style", "markdown_content": _style("bom-style")}],
        "workflows": [],
    }
    result = import_catalog_bundle(
        "\ufeff" + json.dumps(payload),
        style_catalog=styles,
        workflow_catalog=workflows,
    )
    assert result["imported_styles"] == 1
    assert (tmp_path / "styles" / "bom-style.md").is_file()


def _api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    return TestClient(create_app())


def test_bundle_routes_export_download_and_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _api_client(tmp_path, monkeypatch)
    exported = client.get("/api/v1/system/opencode/bundle/export")
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["schema_version"] == 1
    assert any(item["id"] == "canal-paula-reels" for item in payload["styles"])
    assert any(item["id"] == "youtube-longform" for item in payload["workflows"])

    download = client.get(
        "/api/v1/system/opencode/bundle/export", params={"download": "true"}
    )
    assert download.headers["content-disposition"] == (
        'attachment; filename="videoflow-styles-workflows.json"'
    )

    workspace = tmp_path / "workspace"
    response = client.post(
        "/api/v1/system/opencode/bundle/import",
        json={
            "bundle": {
                "schema_version": 1,
                "styles": [
                    {"id": "api-bundle", "markdown_content": _style("api-bundle")}
                ],
                "workflows": [
                    {"id": "api-flow", "markdown_content": _workflow("api-flow")}
                ],
            },
            "overwrite": True,
            "workspace_dir": str(workspace),
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["imported_styles"] == 1
    assert result["imported_workflows"] == 1
    assert result["synced"] is True
    assert (tmp_path / "home" / "styles" / "api-bundle.md").is_file()
    assert (workspace / "presets" / "api-bundle.md").is_file()
    assert (workspace / ".opencode" / "workflows" / "api-flow.md").is_file()


def test_bundle_import_route_returns_422_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _api_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/v1/system/opencode/bundle/import",
        json={
            "bundle": {
                "schema_version": 1,
                "styles": [
                    {"id": "never", "markdown_content": _style("never")}
                ],
                "workflows": [
                    {"id": "bad", "markdown_content": "no frontmatter"}
                ],
            }
        },
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "invalid_catalog_bundle"
    assert not (tmp_path / "home" / "styles" / "never.md").is_file()

    empty = client.post(
        "/api/v1/system/opencode/bundle/import",
        json={"bundle": {"schema_version": 1, "styles": [], "workflows": []}},
    )
    assert empty.status_code == 422
    assert empty.json()["error_code"] == "invalid_catalog_bundle"
