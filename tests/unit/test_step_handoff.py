from pathlib import Path
from types import SimpleNamespace

from videoflow.application.jobs import Job, JobManager
from videoflow.application.projects import init_project
from videoflow.application.step_state import load_step_state, save_step_state
from videoflow.steps.base import EmptyParams


def test_step_job_hydrates_and_persists_project_artifacts(tmp_path: Path, monkeypatch) -> None:
    record, _ = init_project(output=tmp_path / "out")
    output = Path(record.output)
    music = output / "audio" / "music.wav"
    music.parent.mkdir(parents=True)
    music.write_bytes(b"music")
    save_step_state(output, {"audio_music": str(music)})
    seen: dict[str, str] = {}

    class FakeStep:
        params_model = EmptyParams
        type = "test.step"

        def run(self, context, params, io):
            seen.update(context.artifacts)
            target = context.output / "audio" / "next.wav"
            target.write_bytes(b"next")
            context.artifacts["next_audio"] = str(target)

    monkeypatch.setattr("videoflow.steps.registry.get_step", lambda step_type: FakeStep())
    job = Job(
        source=output / "source.mp4",
        output=output,
        options={"step_type": "test.step", "project_id": record.project_id},
        project_id=record.project_id,
    )
    callbacks = SimpleNamespace(
        progress=lambda *args: None,
        step_progress=lambda *args: None,
        should_cancel=lambda: False,
        log=lambda *args: None,
    )

    JobManager(store_dir=None)._run_step(job, callbacks)

    assert seen["audio_music"] == str(music)
    artifacts, _ = load_step_state(output)
    assert artifacts["audio_music"] == str(music)
    assert artifacts["next_audio"] == str(output / "audio" / "next.wav")
