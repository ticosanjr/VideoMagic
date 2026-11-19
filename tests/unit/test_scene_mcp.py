from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.projects import init_project
from videoflow.application.scene_intel.manifest import save_manifest
from videoflow.application.scene_intel.proxy import scene_workspace
from videoflow.domain.scenes import SceneEntry, ScenesManifest
from videoflow.mcp_server.context import ToolContext
from videoflow.mcp_server.scene_tools import register_scene_tools


class FakeManager:
    def __init__(self) -> None:
        self.started: dict[str, object] = {}

    def start(self, source, output, options, **kwargs):
        self.started = {
            "source": Path(source),
            "output": Path(output),
            "options": options,
            "kwargs": kwargs,
        }

        job_output = Path(output)
        job_source = Path(source)

        class Job:
            job_id = "scene-job"
            project_id = options["project_id"]
            output = job_output
            source = job_source
            status = "queued"

            def to_dict(self) -> dict[str, object]:
                return {
                    "job_id": self.job_id,
                    "project_id": self.project_id,
                    "status": self.status,
                    "options": dict(options),
                }

        return Job()


def _build_project(tmp_path: Path, monkeypatch) -> tuple[str, Path]:
    monkeypatch.setenv("VIDEOWFLOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    record, _ = init_project(output=tmp_path / "out")
    return record.project_id, Path(record.output)


def _write_scene_cache(output: Path) -> None:
    workspace = scene_workspace(output / "scenes", "sha-mcp")
    manifest = ScenesManifest(
        video_id="sha-mcp",
        resolution={"w": 1920, "h": 1080},
        fps_num=30,
        fps_den=1,
        scenes=[
            SceneEntry(
                scene_id="SC_0001",
                start_sample=0,
                end_sample=48_000,
                start_sec=0.0,
                end_sec=1.0,
                layout_type="TALKING_HEAD",
                face_count=1,
                face_bbox_norm={"cx": 0.5, "cy": 0.4, "w": 0.2, "h": 0.3},
                face_area_ratio=0.06,
                edge_density=0.02,
                sharpness_laplacian=120.0,
                keyframe_path=str(workspace.keyframes / "SC_0001.jpg"),
                editing_hints=["SAFE_FOR_BROLL"],
            )
        ],
    )
    workspace.keyframes.mkdir(parents=True, exist_ok=True)
    (workspace.keyframes / "SC_0001.jpg").write_bytes(b"jpg")
    save_manifest(
        workspace,
        manifest,
        key="key-mcp",
        engine="pyscenedetect",
        warnings=[],
        elapsed_sec=0.5,
    )
    (workspace.supercontext).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "video_id": "sha-mcp",
                "scenes": [{"scene_id": "SC_0001"}],
                "asus": [],
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )


def _tools(monkeypatch) -> tuple[dict, FakeManager]:
    tools: dict = {}
    manager = FakeManager()

    def register(func):
        tools[func.__name__] = func
        return func

    register_scene_tools(
        register,
        ToolContext(manager=manager),  # type: ignore[arg-type]
        wait_fn=lambda *args: {"ok": True, "job": {"status": "succeeded"}},
    )
    return tools, manager


def test_vf_scenes_manifest_keyframe_supercontext_and_cache(
    tmp_path: Path, monkeypatch
) -> None:
    project_id, output = _build_project(tmp_path, monkeypatch)
    _write_scene_cache(output)
    tools, _manager = _tools(monkeypatch)

    manifest = tools["vf_scenes"](action="manifest", project_id=project_id)
    assert manifest["ok"] is True
    assert manifest["summary"]["scene_count"] == 1
    assert manifest["scenes"][0]["scene_id"] == "SC_0001"
    assert manifest["total"] == 1
    assert manifest["next_offset"] is None

    keyframe = tools["vf_scenes"](
        action="keyframe", project_id=project_id, scene_id="SC_0001"
    )
    assert keyframe["ok"] is True
    assert keyframe["exists"] is True
    assert keyframe["image_returned"] is False
    assert Path(keyframe["keyframe_path"]).is_file()

    missing = tools["vf_scenes"](
        action="keyframe", project_id=project_id, scene_id="SC_9999"
    )
    assert missing["ok"] is False
    assert missing["code"] == "scene_not_found"

    supercontext = tools["vf_scenes"](action="supercontext", project_id=project_id)
    assert supercontext["ok"] is True
    assert supercontext["supercontext"]["scenes"][0]["scene_id"] == "SC_0001"

    cache = tools["vf_scenes"](action="cache", project_id=project_id)
    assert cache["ok"] is True
    assert cache["cache"]["valid"] is True
    assert cache["cache"]["cache_key"] == "key-mcp"


def test_vf_scenes_analyze_starts_scene_step(tmp_path: Path, monkeypatch) -> None:
    project_id, output = _build_project(tmp_path, monkeypatch)
    _write_scene_cache(output)
    tools, manager = _tools(monkeypatch)

    response = tools["vf_scenes"](
        action="analyze",
        project_id=project_id,
        compute_policy="local",
        threshold=2.5,
        force=True,
    )
    assert response["ok"] is True
    assert response["wait"]["ok"] is True
    assert response["scenes"]["scene_count"] == 1
    options = manager.started["options"]
    assert options["mode"] == "step"
    assert options["step_type"] == "scene.analyze"
    assert options["params"]["threshold"] == 2.5
    assert options["params"]["compute_policy"] == "local"


def test_vf_scenes_reports_missing_manifest(tmp_path: Path, monkeypatch) -> None:
    project_id, _output = _build_project(tmp_path, monkeypatch)
    tools, _manager = _tools(monkeypatch)
    response = tools["vf_scenes"](action="manifest", project_id=project_id)
    assert response["ok"] is False
    assert response["code"] == "scenes_missing"


def test_scene_resources_return_manifest_and_keyframe_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    import asyncio

    from videoflow.mcp_server.server import build_server

    project_id, output = _build_project(tmp_path, monkeypatch)
    _write_scene_cache(output)

    async def read(uri: str) -> str:
        contents = await build_server().read_resource(uri)
        return next(iter(contents)).content  # type: ignore[attr-defined]

    manifest = json.loads(
        asyncio.run(read(f"vf://projects/{project_id}/scenes"))
    )
    assert manifest["ok"] is True
    assert manifest["manifest"]["scenes"][0]["scene_id"] == "SC_0001"

    keyframe = json.loads(
        asyncio.run(
            read(f"vf://projects/{project_id}/scenes/SC_0001/keyframe")
        )
    )
    assert keyframe["ok"] is True
    assert keyframe["exists"] is True
    assert keyframe["image_returned"] is False

    missing = json.loads(
        asyncio.run(
            read(f"vf://projects/{project_id}/scenes/SC_9999/keyframe")
        )
    )
    assert missing["ok"] is False
    assert missing["code"] == "scene_not_found"
