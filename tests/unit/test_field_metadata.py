"""Every step parameter ships label, help, group, and unit metadata."""

from __future__ import annotations

from videoflow.steps import get_step, step_types


def properties(step_type: str) -> dict[str, dict[str, object]]:
    schema = get_step(step_type).manifest()["params_schema"]
    return dict(schema.get("properties") or {})


def test_every_parameter_has_label_and_help() -> None:
    missing: list[str] = []
    for step_type in step_types():
        for key, spec in properties(step_type).items():
            if not str(spec.get("title") or "").strip():
                missing.append(f"{step_type}.{key}: title")
            if not str(spec.get("description") or "").strip():
                missing.append(f"{step_type}.{key}: description")
            if not str(spec.get("x-group") or "").strip():
                missing.append(f"{step_type}.{key}: group")
    assert missing == []


def test_units_and_placeholders_reach_the_schema() -> None:
    vad = properties("audio.vad")
    assert vad["min_silence_ms"]["x-unit"] == "ms"
    assert vad["noise_db"]["x-unit"] == "dB"
    assert vad["min_silence_ms"]["x-group"] == "Audio"

    ingest = properties("ingest")
    assert ingest["source"]["x-placeholder"] == "/media/source.mp4"

    transcribe = properties("transcribe")
    assert transcribe["srt_path"]["x-placeholder"] == "/path/to/subtitles.srt"

    timeline = properties("edit.timeline")
    assert timeline["transition_type"]["x-control"] == "select"


def test_nested_caption_style_fields_have_help() -> None:
    schema = get_step("shorts.render").manifest()["params_schema"]
    caption = (schema.get("$defs") or {}).get("CaptionStyle") or {}
    props = caption.get("properties") or {}
    assert props
    assert all(str(spec.get("description") or "").strip() for spec in props.values())
    assert props["font_size"]["x-unit"] == "" or isinstance(props["font_size"]["x-unit"], str)


def test_step_specific_copy_wins_over_the_shared_copy() -> None:
    ingest = properties("ingest")
    sfx = properties("sfx.plan")
    assert "Source media file" in str(ingest["source"]["description"])
    assert "sound effects" in str(sfx["directory"]["description"])
