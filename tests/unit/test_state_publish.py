from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.domain.state import MediaInfo, ProjectState
from videoflow.engine.runner import persist_project_state


def context(tmp_path: Path, revision: int) -> PipelineContext:
    output = tmp_path / "out"
    return PipelineContext(
        source=tmp_path / "source.mp4",
        output=output,
        work=output / "work",
        exports=output / "exports",
        state=ProjectState(
            revision=revision,
            media_info=MediaInfo(
                source_path=str(tmp_path / "source.mp4"),
                duration_frames=30,
                fps_num=30,
                fps_den=1,
                width=320,
                height=240,
                audio_sample_rate=48000,
            ),
        ),
    )


def test_project_state_is_published_atomically(tmp_path: Path) -> None:
    ctx = context(tmp_path, 1)
    path = persist_project_state(ctx)
    assert path is not None
    assert path.is_file()
    assert ProjectState.model_validate_json(path.read_text(encoding="utf-8")).revision == 1


def test_project_state_does_not_clobber_newer_manual_edits(tmp_path: Path) -> None:
    ctx = context(tmp_path, 1)
    path = persist_project_state(ctx)
    assert path is not None
    newer = ctx.state.model_copy(update={"revision": 7})
    path.write_text(newer.model_dump_json(), encoding="utf-8")

    persist_project_state(ctx)

    assert ProjectState.model_validate_json(path.read_text(encoding="utf-8")).revision == 7


def test_publish_is_a_noop_without_a_state(tmp_path: Path) -> None:
    ctx = context(tmp_path, 1)
    ctx.state = None
    assert persist_project_state(ctx) is None
