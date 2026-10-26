"""Short re-editing: validation, trims, captions, and result updates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from videoflow.application import short_editor
from videoflow.application.short_editor import ShortEditOptions, edit_short
from videoflow.domain.errors import ShortEditError, StateNotReadyError
from videoflow.domain.state import MediaInfo, ProjectState, Sentence

RATE = 48000


def media() -> MediaInfo:
    return MediaInfo(
        source_path="/tmp/source.mp4",
        duration_frames=100,
        fps_num=25,
        fps_den=1,
        width=640,
        height=360,
        audio_sample_rate=RATE,
    )


def project(
    tmp_path: Path,
    *,
    pieces: list[list[int]] | None = None,
    entry: dict | None = None,
    transcript: list[Sentence] | None = None,
    state: ProjectState | None = None,
) -> tuple[Path, dict]:
    output = tmp_path / "out"
    output.mkdir(parents=True, exist_ok=True)
    state = state or ProjectState(
        media_info=media(),
        transcript=transcript
        if transcript is not None
        else [Sentence(id=0, start_sample=0, end_sample=2 * RATE, text="Hello world.")],
    )
    (output / "project_state.json").write_text(state.model_dump_json(), encoding="utf-8")
    clip = {
        "title": "Old title",
        "pieces": pieces if pieces is not None else [[0, 2 * RATE]],
        "aspect_ratio": "9:16",
        "path": str(output / "old.mp4"),
        "subtitles": str(output / "old.ass"),
        "edit_count": 1,
        "crop_focus_x": 0.25,
    }
    if entry:
        clip.update(entry)
    (output / "shorts.json").write_text(
        json.dumps({"ok": True, "clips": [clip]}), encoding="utf-8"
    )
    return output, {"shorts": [dict(clip)]}


class FakeAdapter:
    calls: list[dict[str, object]] = []

    def render_short(
        self, _source: Path, pieces: object, destination: Path, **kwargs: object
    ) -> Path:
        self.calls.append({"pieces": pieces, **kwargs})
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"mp4")
        return destination


def test_edit_validates_the_index_and_entry(tmp_path: Path) -> None:
    output, result = project(tmp_path)

    with pytest.raises(ShortEditError, match="out of range"):
        edit_short(
            source=tmp_path / "source.mp4",
            output=output,
            index=4,
            result=result,
            options=ShortEditOptions(),
        )
    with pytest.raises(ShortEditError, match="invalid"):
        edit_short(
            source=tmp_path / "source.mp4",
            output=output,
            index=0,
            result={"shorts": ["not a dict"]},
            options=ShortEditOptions(),
        )


def test_edit_requires_a_completed_project(tmp_path: Path) -> None:
    output = tmp_path / "missing"
    output.mkdir()
    result = {"shorts": [{"pieces": [[0, 10]]}]}

    with pytest.raises(StateNotReadyError, match="Cannot read"):
        edit_short(
            source=tmp_path / "source.mp4",
            output=output,
            index=0,
            result=result,
            options=ShortEditOptions(),
        )


def test_edit_requires_media_and_pieces(tmp_path: Path) -> None:
    output, result = project(tmp_path, state=ProjectState())

    with pytest.raises(StateNotReadyError, match="no media metadata"):
        edit_short(
            source=tmp_path / "source.mp4",
            output=output,
            index=0,
            result=result,
            options=ShortEditOptions(),
        )

    output, result = project(tmp_path / "pieces", pieces=[])
    with pytest.raises(ShortEditError, match="no source pieces"):
        edit_short(
            source=tmp_path / "source.mp4",
            output=output,
            index=0,
            result=result,
            options=ShortEditOptions(),
        )

    output, result = project(tmp_path / "bad", pieces=[["x", 1]])
    with pytest.raises(ShortEditError, match="pieces are invalid"):
        edit_short(
            source=tmp_path / "source.mp4",
            output=output,
            index=0,
            result=result,
            options=ShortEditOptions(),
        )


def test_edit_rejects_a_trim_without_video(tmp_path: Path) -> None:
    output, result = project(tmp_path)

    with pytest.raises(ShortEditError, match="leaves no video"):
        edit_short(
            source=tmp_path / "source.mp4",
            output=output,
            index=0,
            result=result,
            options=ShortEditOptions(start_sec=1.0, end_sec=1.0),
        )


def test_edit_renders_and_updates_the_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, result = project(tmp_path)
    FakeAdapter.calls = []
    monkeypatch.setattr(short_editor, "FFmpegAdapter", FakeAdapter)
    monkeypatch.setattr(short_editor, "fonts_dir", lambda: tmp_path / "fonts")
    monkeypatch.setattr(short_editor, "images_dir", lambda: tmp_path / "images")
    monkeypatch.setattr(short_editor, "music_dir", lambda: tmp_path / "music")

    entry = edit_short(
        source=tmp_path / "source.mp4",
        output=output,
        index=0,
        result=result,
        options=ShortEditOptions(
            title="New title",
            start_sec=0.25,
            end_sec=1.5,
            aspect_ratio="1:1",
        ),
    )

    assert entry["title"] == "New title"
    assert entry["aspect_ratio"] == "1:1"
    assert entry["width"] == entry["height"] == 1080
    assert entry["edit_count"] == 2
    assert entry["previous_path"].endswith("old.mp4")
    assert entry["sentence_ids"] == [0]
    assert entry["start_sec"] == 0.25
    assert entry["end_sec"] == 1.5
    assert Path(str(entry["path"])).is_file()
    assert Path(str(entry["subtitles"])).is_file()
    assert FakeAdapter.calls[0]["crop_focus_x"] == 0.25
    report = json.loads((output / "shorts.json").read_text(encoding="utf-8"))
    assert report["clips"][0]["title"] == "New title"
    assert result["shorts"][0]["title"] == "New title"


def test_edit_can_disable_subtitles_and_rejects_bad_styles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, result = project(tmp_path)
    monkeypatch.setattr(short_editor, "FFmpegAdapter", FakeAdapter)
    monkeypatch.setattr(short_editor, "fonts_dir", lambda: tmp_path / "fonts")

    entry = edit_short(
        source=tmp_path / "source.mp4",
        output=output,
        index=0,
        result=result,
        options=ShortEditOptions(burn_subtitles=False),
    )

    assert "subtitles" not in entry

    with pytest.raises(ShortEditError, match="Invalid caption style"):
        edit_short(
            source=tmp_path / "source.mp4",
            output=output,
            index=0,
            result=result,
            options=ShortEditOptions(caption_style={"font_size": "huge"}),
        )


def test_edit_accepts_an_entry_caption_style(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, result = project(tmp_path, entry={"caption_style": {"font_size": 90}})
    monkeypatch.setattr(short_editor, "FFmpegAdapter", FakeAdapter)
    monkeypatch.setattr(short_editor, "fonts_dir", lambda: tmp_path / "fonts")

    entry = edit_short(
        source=tmp_path / "source.mp4",
        output=output,
        index=0,
        result=result,
        options=ShortEditOptions(),
    )

    assert entry["caption_style"]["font_size"] == 90


def test_edit_wires_optional_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, result = project(tmp_path)
    state = ProjectState(media_info=media())
    state.modules_config.overlay.enabled = True
    state.modules_config.overlay.asset = "logo.png"
    state.modules_config.music.enabled = True
    state.modules_config.music.asset = "track.wav"
    state.modules_config.intro_outro.intro_enabled = True
    state.modules_config.intro_outro.intro_asset = "intro.mp4"
    state.modules_config.intro_outro.outro_enabled = True
    state.modules_config.intro_outro.outro_asset = "outro.mp4"
    (output / "project_state.json").write_text(state.model_dump_json(), encoding="utf-8")
    FakeAdapter.calls = []
    monkeypatch.setattr(short_editor, "FFmpegAdapter", FakeAdapter)
    monkeypatch.setattr(short_editor, "fonts_dir", lambda: tmp_path / "fonts")
    monkeypatch.setattr(short_editor, "images_dir", lambda: tmp_path / "images")
    monkeypatch.setattr(short_editor, "music_dir", lambda: tmp_path / "music")

    edit_short(
        source=tmp_path / "source.mp4",
        output=output,
        index=0,
        result=result,
        options=ShortEditOptions(burn_subtitles=False),
    )

    call = FakeAdapter.calls[0]
    assert Path(str(call["overlay_path"])).name == "logo.png"
    assert Path(str(call["music_path"])).name == "track.wav"
    assert Path(str(call["intro_path"])).name == "intro.mp4"
    assert Path(str(call["outro_path"])).name == "outro.mp4"


def test_edit_without_transcript_has_no_captions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output, result = project(tmp_path, transcript=[])
    monkeypatch.setattr(short_editor, "FFmpegAdapter", FakeAdapter)
    monkeypatch.setattr(short_editor, "fonts_dir", lambda: tmp_path / "fonts")

    entry = edit_short(
        source=tmp_path / "source.mp4",
        output=output,
        index=0,
        result=result,
        options=ShortEditOptions(),
    )

    assert "subtitles" not in entry
    assert entry["sentence_ids"] == []
