from pathlib import Path

from videoflow.application.step_state import load_step_state, save_step_state


def test_step_state_persists_live_artifacts_and_metadata(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    music = output / "music.wav"
    music.write_bytes(b"music")

    save_step_state(
        output,
        {"audio_music": str(music), "missing": str(output / "missing.wav"), "empty": ""},
        {"audio_music": {"loop_seconds": 5}},
    )

    artifacts, metadata = load_step_state(output)
    assert artifacts == {"audio_music": str(music)}
    assert metadata["audio_music"]["loop_seconds"] == 5

    other = output / "master.wav"
    other.write_bytes(b"master")
    save_step_state(output, {"audio_master": str(other)})
    artifacts, _ = load_step_state(output)
    assert artifacts["audio_music"] == str(music)
    assert artifacts["audio_master"] == str(other)


def test_step_state_drops_missing_paths(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    missing = output / "gone.wav"
    save_step_state(output, {"gone": str(missing)})
    assert load_step_state(output)[0] == {}


def test_step_state_ignores_corrupt_and_non_dict_files(tmp_path: Path) -> None:
    from videoflow.application.step_state import state_path

    output = tmp_path / "out"
    output.mkdir()
    path = state_path(output)
    path.write_text("{", encoding="utf-8")
    assert load_step_state(output) == ({}, {})
    path.write_text("[]", encoding="utf-8")
    assert load_step_state(output) == ({}, {})


def test_step_state_skips_oversized_and_unserializable_metadata(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    save_step_state(output, {}, {"huge": "x" * 3_000_000})
    assert load_step_state(output)[1] == {}

    class Broken:
        def __str__(self) -> str:
            raise ValueError("no")

    save_step_state(output, {}, {"broken": Broken()})
    assert "broken" not in load_step_state(output)[1]


def test_step_state_rejects_paths_outside_project_and_allowed_roots(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"x")
    save_step_state(output, {"outside": str(outside)})
    assert load_step_state(output)[0] == {}
