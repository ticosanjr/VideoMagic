from __future__ import annotations

from pathlib import Path

from videoflow.core.context import PipelineContext
from videoflow.core.recipe import parse_recipe
from videoflow.domain.state import MediaInfo
from videoflow.engine import runner as runner_module
from videoflow.engine.runner import RecipeRunner
from videoflow.steps.base import BaseStep, EmptyParams, StepIO


class FakeAdapter:
    def probe(self, path: Path) -> MediaInfo:
        return MediaInfo(
            source_path=str(path),
            duration_frames=90,
            fps_num=30,
            fps_den=1,
            width=640,
            height=360,
            audio_sample_rate=48000,
        )

    def extract_pcm(self, source: Path, target: Path, *, sample_rate: int) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"pcm")
        return target

    def pcm_digest(self, path: Path) -> str:
        return "digest"


def _recipe() -> object:
    return parse_recipe(
        {
            "schema_version": 1,
            "id": "node_io",
            "name": "Node IO",
            "steps": [{"id": "ingest", "type": "ingest", "params": {}}],
        }
    )


def test_media_override_probes_and_extracts_pcm(tmp_path: Path, monkeypatch) -> None:
    media = tmp_path / "source.mp4"
    media.write_bytes(b"x")
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    runner = RecipeRunner(_recipe(), adapter=FakeAdapter())
    context = PipelineContext(
        source=tmp_path / "unused.mp4",
        output=tmp_path / "out",
        work=tmp_path / "out" / "work",
        exports=tmp_path / "out" / "exports",
    )
    step = runner.recipe.steps[0].model_copy(
        update={"id": "vad", "type": "audio.vad", "media_override": str(media)}
    )
    runner._ensure_media_override(context, step)
    assert context.source == media.resolve()
    assert context.media is not None
    assert context.media.source_path == str(media.resolve())
    assert context.pcm_path is not None and context.pcm_path.is_file()
    assert context.pcm_digest == "digest"


def test_output_folder_copies_step_artifacts(tmp_path: Path, monkeypatch) -> None:
    class Writer(BaseStep):
        type = "ingest"
        params_model = EmptyParams

        def run(self, context, params, io: StepIO) -> None:
            target = context.output / "artifact.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("hello", encoding="utf-8")
            context.artifacts["artifact.txt"] = str(target)

        def cache_outputs(self, context) -> tuple[Path, ...]:
            return (context.output / "artifact.txt",)

    monkeypatch.setattr(runner_module, "get_step", lambda step_type: Writer())
    monkeypatch.setenv("VIDEOWFLOW_ALLOWED_ROOTS", str(tmp_path))
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    recipe = parse_recipe(
        {
            "schema_version": 1,
            "id": "folder_io",
            "name": "Folder IO",
            "steps": [
                {
                    "id": "ingest",
                    "type": "ingest",
                    "output_mode": "folder",
                    "output_dir": str(tmp_path / "exports-final"),
                    "params": {},
                }
            ],
        }
    )
    result = RecipeRunner(recipe).run(source, tmp_path / "out", resume=False)
    copied = tmp_path / "exports-final" / "artifact.txt"
    assert copied.read_text(encoding="utf-8") == "hello"
    assert result.context.artifacts["ingest:artifact.txt"] == str(copied)
    assert result.context.metadata["node_outputs"]["ingest"] == [str(copied)]
