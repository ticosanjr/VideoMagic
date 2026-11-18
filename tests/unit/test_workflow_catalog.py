from pathlib import Path

from videoflow.application import workflow_service
from videoflow.application.workflow_catalog import WorkflowCatalog, seed_workflows_dir


def test_workflow_seeds_are_valid() -> None:
    catalog = WorkflowCatalog(include_seeds=True)
    ids = {item.workflow_id for item in catalog.list_workflows()}
    assert {
        "youtube-longform",
        "reels-from-raw",
        "shorts-from-long",
        "decupagem-limpa",
        "clone-style",
    } <= ids
    workflow = catalog.get("youtube-longform")
    assert workflow.aspect_ratio == "16:9"
    assert workflow.steps


def test_workflow_catalog_crud_and_sync(tmp_path: Path) -> None:
    root = tmp_path / "workflows"
    catalog = WorkflowCatalog(root)
    service = workflow_service

    created = service.save_workflow(
        workflow_id="custom-flow",
        name="Custom Flow",
        catalog=catalog,
    )
    assert created["ok"] is True
    assert (root / "custom-flow.md").is_file()

    duplicate = service.duplicate_workflow(
        "custom-flow", new_id="custom-flow-copy", catalog=catalog
    )
    assert duplicate["ok"] is True
    assert (root / "custom-flow-copy.md").is_file()

    target = tmp_path / "workspace"
    synced = service.sync_workflows(target, overwrite=True, catalog=catalog)
    copied = {Path(item).name for item in synced["sync"]["copied"]}
    assert {"custom-flow.md", "custom-flow-copy.md"} <= copied
    assert (target / ".opencode" / "workflows" / "custom-flow.md").is_file()

    assert service.delete_workflow("custom-flow-copy", catalog=catalog)["deleted"] is True
    restored = service.restore_workflow("youtube-longform", catalog=catalog)
    assert restored["ok"] is True
    assert (root / "youtube-longform.md").is_file()


def test_workflow_seed_directory_has_markdown() -> None:
    seeds = list(seed_workflows_dir().glob("*.md"))
    assert len(seeds) == 5


def test_workflow_invalid_frontmatter_and_missing_paths(tmp_path: Path) -> None:
    import pytest

    from videoflow.application.workflow_catalog import (
        parse_workflow_markdown,
        workflow_id_from_name,
    )
    from videoflow.domain.errors import StyleError, StyleNotFoundError

    with pytest.raises(StyleError, match="frontmatter"):
        parse_workflow_markdown("# no frontmatter")
    with pytest.raises(StyleError, match="not closed"):
        parse_workflow_markdown("---\nworkflow_id: x\n")

    root = tmp_path / "workflows"
    catalog = WorkflowCatalog(root)
    with pytest.raises(StyleNotFoundError):
        catalog.get("missing")
    assert catalog.delete("missing") is False
    with pytest.raises(StyleNotFoundError):
        catalog.restore_seed("missing")
    assert workflow_id_from_name("!!!").startswith("workflow-")


def test_workflow_sync_respects_selection_and_skips_existing(tmp_path: Path) -> None:
    root = tmp_path / "workflows"
    catalog = WorkflowCatalog(root)
    workflow_service.save_workflow(workflow_id="one", name="One", catalog=catalog)
    workflow_service.save_workflow(workflow_id="two", name="Two", catalog=catalog)
    target = tmp_path / "workspace"
    first = catalog.sync(target, workflow_ids=["one"])
    assert [Path(item).name for item in first["copied"]] == ["one.md"]
    second = catalog.sync(target, workflow_ids=["one"])
    assert second["copied"] == []
    assert second["skipped"]
    assert catalog.get("one").name == "One"
    assert catalog.path_for("missing").name == "missing.md"


def test_workflow_service_validates_markdown_and_can_sync(tmp_path: Path) -> None:
    import pytest

    from videoflow.domain.errors import StyleError

    root = tmp_path / "workflows"
    catalog = WorkflowCatalog(root)
    with pytest.raises(StyleError):
        workflow_service.save_workflow(
            workflow_id="bad",
            markdown_content="no frontmatter",
            catalog=catalog,
        )
    saved = workflow_service.save_workflow(
        workflow_id="good",
        name="Good",
        workspace_dir=tmp_path / "workspace",
        catalog=catalog,
    )
    assert saved["workflow"]["name"] == "Good"
    assert saved["sync"]["copied"]


def test_workflow_parser_and_service_edge_cases(tmp_path: Path) -> None:
    import pytest

    from videoflow.application.workflow_catalog import (
        WorkflowCatalog,
        catalog,
        parse_workflow_markdown,
        workflow_id_from_name,
    )
    from videoflow.domain.errors import StyleError
    from videoflow.domain.workflows import WorkflowDefinition, WorkflowStep

    with pytest.raises(StyleError, match="frontmatter is not closed"):
        parse_workflow_markdown("---\nworkflow_id: x")
    with pytest.raises(StyleError, match="invalid workflow frontmatter"):
        parse_workflow_markdown("---\nworkflow_id: [\n---\nbody")
    with pytest.raises(StyleError, match="mapping"):
        parse_workflow_markdown("---\n- a\n---\nbody")
    with pytest.raises(StyleError, match="invalid workflow definition"):
        parse_workflow_markdown("---\nworkflow_id: BAD ID\n---\nbody")

    assert workflow_id_from_name("!!!").startswith("workflow-")
    assert catalog().list_workflows()

    root = tmp_path / "workflows"
    active = WorkflowCatalog(root)
    workflow = WorkflowDefinition(
        workflow_id="lock",
        name="Lock",
        steps=[WorkflowStep(id="one", node="ingest")],
    )
    active.save(workflow)
    with pytest.raises(StyleError, match="already exists"):
        active.save(workflow, overwrite=False)

    rendered = workflow_service.save_workflow(
        workflow_id="with-body",
        markdown_content=("---\nworkflow_id: with-body\nname: With Body\n---\n\nBody\n"),
        catalog=active,
    )
    assert rendered["workflow"]["body"].strip() == "Body"
    updated = workflow_service.save_workflow(
        workflow_id="with-body",
        name="Renamed",
        updates={"description": "desc"},
        catalog=active,
    )
    assert updated["workflow"]["description"] == "desc"


def test_workflow_parser_fallback_and_read_error(tmp_path: Path) -> None:
    import pytest

    from videoflow.application import workflow_catalog
    from videoflow.application.workflow_catalog import parse_workflow_markdown
    from videoflow.domain.errors import StyleError
    from videoflow.domain.workflows import WorkflowDefinition

    parsed = parse_workflow_markdown("---\nname: Fallback\n---\nbody", fallback_id="fallback")
    assert parsed.workflow_id == "fallback"
    folder = tmp_path / "bad.md"
    folder.mkdir()
    with pytest.raises(StyleError, match="cannot read workflow"):
        workflow_catalog._read(folder)

    workflow = WorkflowDefinition(
        workflow_id="dupes",
        name="Dupes",
        export_targets=["resolve", "resolve", "premiere"],
    )
    assert workflow.export_targets == ["resolve", "premiere"]
