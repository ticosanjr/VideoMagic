"""Project registry, artifact access, and session discovery edge cases."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from videoflow.application import artifacts, database
from videoflow.application.projects import (
    get_project,
    init_project,
    list_projects,
    load_project_state,
    project_for_output,
    save_project_state,
    state_path,
)
from videoflow.domain.errors import IngestError, ProjectStateError, StateNotReadyError


def _clip(path: Path, seconds: float = 0.5) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=160x120:rate=30:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


def test_project_registry_and_revision_conflict(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    record, state = init_project(name="Demo", output=tmp_path / "out")
    assert get_project(record.project_id).name == "Demo"
    assert list_projects()
    assert project_for_output(tmp_path / "out") is not None
    loaded = load_project_state(record)
    assert loaded.project_id == state.project_id
    updated = save_project_state(record, loaded, bump_revision=True)
    assert updated.revision == loaded.revision + 1
    with pytest.raises(ProjectStateError):
        save_project_state(record, updated, expected_revision=1)
    with pytest.raises(ProjectStateError):
        get_project("missing")
    missing_state = record.model_copy(
        update={
            "project_id": "00000000-0000-0000-0000-000000000000",
            "output": str(tmp_path / "missing"),
        }
    )
    with pytest.raises(StateNotReadyError):
        load_project_state(missing_state)
    assert state_path(record).name == "project_state.json"


def test_project_database_functions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    database.upsert_project("p1", {"project_id": "p1", "name": "One"})
    assert database.get_project("p1")["name"] == "One"
    assert database.list_projects()[0]["project_id"] == "p1"
    assert database.get_project("missing") is None
    database.upsert_job("j1", {"job_id": "j1", "status": "queued", "project_id": "p1"})
    assert database.list_jobs()[0]["project_id"] == "p1"


def test_artifact_manifest_and_errors(tmp_path: Path) -> None:
    from PIL import Image

    out = tmp_path / "out"
    (out / "exports").mkdir(parents=True)
    (out / "work" / "qa").mkdir(parents=True)
    (out / "exports" / "note.txt").write_text("hello", encoding="utf-8")
    Image.new("RGB", (8, 8)).save(out / "exports" / "frame.png")
    Image.new("RGB", (8, 8)).save(out / "work" / "qa" / "failed.jpg")
    (out / "work" / "qa" / "qa_report.json").write_text(
        json.dumps({"defects": [{"kind": "flash"}], "passed": False}),
        encoding="utf-8",
    )
    (out / "work" / "qa" / "safezone.json").write_text(
        json.dumps({"collisions": [{"platform": "reels"}]}), encoding="utf-8"
    )
    items = artifacts.list_artifacts(out, include_hash=True)
    assert any(item["kind"] == "image" for item in items)
    ids = {item["relative_path"]: item["artifact_id"] for item in items}
    assert artifacts.find_artifact(out, ids["exports/note.txt"]).is_file()
    assert artifacts.find_artifact(out, "note.txt").is_file()
    assert artifacts.artifact_payload(out, out / "exports" / "note.txt")["text"] == "hello"
    qa = artifacts.qa_artifacts(out)
    assert qa["defects"]
    assert qa["frames"]
    with pytest.raises(ProjectStateError):
        artifacts.find_artifact(out, "missing")
    with pytest.raises(ProjectStateError):
        artifacts.find_artifact(out, "")


def test_session_discovery_orders_and_errors(tmp_path: Path, monkeypatch) -> None:
    from videoflow.steps.session_ingest import (
        SessionIngestParams,
        _discover,
        _sha256,
        _sort,
    )

    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    one = _clip(tmp_path / "clip10.mp4")
    two = _clip(tmp_path / "clip2.mp4")
    assert _sort([one, two], "name")[0].name == "clip2.mp4"
    assert _sort([one, two], "mtime")[0].name in {"clip10.mp4", "clip2.mp4"}
    assert _sort([one, two], "timecode")
    assert _sort([one, two], "auto")
    discovered = _discover(SessionIngestParams(raw_dir=str(tmp_path), sources=[str(one), str(one)]))
    assert len(discovered) == 2
    assert _sha256(one)
    with pytest.raises(IngestError):
        _discover(SessionIngestParams(raw_dir=str(tmp_path / "missing")))
    with pytest.raises(IngestError):
        _discover(SessionIngestParams(sources=[]))


def test_database_migration_and_malformed_payloads(tmp_path: Path, monkeypatch) -> None:
    import sqlite3

    home = tmp_path / "home"
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(home))
    (home / "jobs").mkdir(parents=True)
    (home / "batches").mkdir()
    (home / "jobs" / "j1.json").write_text(
        json.dumps({"job_id": "j1", "status": "succeeded"}), encoding="utf-8"
    )
    (home / "jobs" / "bad.json").write_text("{", encoding="utf-8")
    (home / "assets.json").write_text(
        json.dumps({"assets": [{"id": "a1"}, "bad"]}), encoding="utf-8"
    )
    (home / "batches" / "b1.json").write_text(json.dumps({"batch_id": "b1"}), encoding="utf-8")
    (home / "batches" / "bad.json").write_text("{", encoding="utf-8")
    migrated = database.migrate_home()["imported"]
    assert migrated["jobs"] >= 1
    assert migrated["assets"] >= 1
    assert migrated["batches"] >= 1

    with sqlite3.connect(database.db_path()) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO projects (project_id, payload, updated_at) VALUES (?, ?, ?)",
            ("broken", "{", "now"),
        )
        connection.execute(
            "INSERT OR REPLACE INTO projects (project_id, payload, updated_at) VALUES (?, ?, ?)",
            ("list", "[]", "now"),
        )
    assert database.get_project("broken") is None
    assert database.get_project("list") is None
    assert database.list_projects() == []


def test_artifact_kinds_and_unreadable_qa(tmp_path: Path) -> None:
    out = tmp_path / "out"
    (out / "exports").mkdir(parents=True)
    (out / "work" / "qa").mkdir(parents=True)
    (out / "exports" / "a.wav").write_bytes(b"wav")
    (out / "exports" / "b.mp4").write_bytes(b"mp4")
    (out / "exports" / "c.bin").write_bytes(b"bin")
    (out / "work" / "qa" / "qa_report.json").write_text("{", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    kinds = {item["name"]: item["kind"] for item in artifacts.list_artifacts(out)}
    assert kinds["a.wav"] == "audio"
    assert kinds["b.mp4"] == "video"
    assert kinds["c.bin"] == "file"
    assert artifacts.find_artifact(out, str(out / "exports" / "a.wav")).is_file()
    outside_id = artifacts.artifact_id(out, outside)
    assert outside_id
    assert artifacts.qa_artifacts(out)["reports"]["qa_report"] == {"error": "unreadable"}


def test_project_id_helper() -> None:
    from videoflow.application.projects import project_uuid

    assert str(project_uuid("fixed")) == str(project_uuid("fixed"))
    assert project_uuid("fixed") != project_uuid("other")
    assert project_uuid("6f0d5c4e-2b6c-4a3f-9d8f-3b7e7f2d1a10") == project_uuid(
        "6f0d5c4e-2b6c-4a3f-9d8f-3b7e7f2d1a10"
    )
    assert project_uuid()


def test_project_file_adoption_and_corruption(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home-file"))
    out = tmp_path / "external"
    out.mkdir()
    record = {
        "project_id": "p-file",
        "name": "File",
        "output": str(out),
    }
    (out / "project.json").write_text(json.dumps(record), encoding="utf-8")
    loaded = project_for_output(out)
    assert loaded is not None
    assert loaded.project_id == "p-file"
    (out / "project.json").write_text("{", encoding="utf-8")
    assert project_for_output(out) is None


def test_load_project_state_rejects_v1_source(tmp_path: Path, monkeypatch) -> None:
    from videoflow.application.projects import ProjectRecord, load_project_state
    from videoflow.domain.errors import ProjectStateError

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home-v1"))
    output = tmp_path / "v1"
    output.mkdir()
    (output / "project_state.json").write_text(
        '{"schema_version": 1, "project_id": "8d1d4f0e-8b1e-4d7a-9e6f-5b2d1c0a3f11"}',
        encoding="utf-8",
    )
    record = ProjectRecord(
        project_id="8d1d4f0e-8b1e-4d7a-9e6f-5b2d1c0a3f11",
        name="v1",
        output=str(output),
    )
    with pytest.raises(ProjectStateError):
        load_project_state(record)

def test_project_mirrors_state_into_workspace(tmp_path: Path, monkeypatch) -> None:
    from vf_contracts.workspace import project_dir

    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home-ws"))
    record, state = init_project(name="Workspace", output=tmp_path / "out-ws")
    folder = project_dir(record.project_id)
    assert (folder / "project.json").is_file()
    assert (folder / "state.json").is_file()
    assert (folder / "assets" / "voice").is_dir()
    assert (folder / "captions").is_dir()
    assert (folder / "renders" / "final").is_dir()
    metadata = json.loads((folder / "project.json").read_text(encoding="utf-8"))
    assert metadata["name"] == "Workspace"
    assert metadata["project_id"] == record.project_id
    assert metadata["state_path"] == str(folder / "state.json")
    assert state.revision == 1
