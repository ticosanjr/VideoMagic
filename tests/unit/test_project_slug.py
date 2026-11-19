from __future__ import annotations

from pathlib import Path

from videoflow.application.projects import (
    clone_project,
    get_project,
    init_project,
    project_uuid,
)


def test_slug_project_keeps_slug_and_deterministic_state_uuid(tmp_path: Path) -> None:
    record, state = init_project(
        project_id="meu-slug",
        name="Slug",
        output=tmp_path / "slug",
    )
    assert record.project_id == "meu-slug"
    assert state.project_id == project_uuid("meu-slug")
    assert get_project("meu-slug").project_id == "meu-slug"
    assert project_uuid("meu-slug") == project_uuid("meu-slug")
    assert project_uuid("meu-slug") != project_uuid("outro-slug")


def test_adopted_slug_output_keeps_slug(tmp_path: Path) -> None:
    from videoflow.application import database

    output = tmp_path / "adopted"
    init_project(project_id="adotado", name="Adotado", output=output)
    database.delete_project("adotado")
    (output / "project.json").unlink()
    record, state = init_project(project_id="adotado", name="Adotado", output=output)
    assert record.project_id == "adotado"
    assert state.project_id == project_uuid("adotado")


def test_clone_accepts_a_target_slug(tmp_path: Path) -> None:
    record, _ = init_project(
        project_id="origem",
        name="Origem",
        output=tmp_path / "origem",
    )
    cloned, state = clone_project(
        record,
        name="Clonado",
        output=str(tmp_path / "clonado"),
        project_id="clonado",
    )
    assert cloned.project_id == "clonado"
    assert state.project_id == project_uuid("clonado")
    assert get_project("clonado").project_id == "clonado"
