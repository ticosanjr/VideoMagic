import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from videoflow.domain.presets import (
    SHIPPED_PRESET_NAMES,
    load_preset,
    load_shipped_presets,
)


def test_all_shipped_presets_validate() -> None:
    presets = load_shipped_presets()
    assert tuple(preset.name for preset in presets) == SHIPPED_PRESET_NAMES


def test_youtube_preset_disables_shorts_and_keeps_cpu_defaults() -> None:
    presets = {preset.name: preset for preset in load_shipped_presets()}
    youtube = presets["youtube-talking-head"]
    assert youtube.module_enabled.shorts is False
    assert youtube.modules_config.transcribe.device == "cpu"


def test_lecture_preset_is_conservative() -> None:
    presets = {preset.name: preset for preset in load_shipped_presets()}
    lecture = presets["lecture-clean"]
    assert lecture.modules_config.zooms.progressive_zoom is False
    assert lecture.modules_config.jl_cuts.enable_j_cuts is False


def test_shorts_preset_requests_three_vertical_clips() -> None:
    presets = {preset.name: preset for preset in load_shipped_presets()}
    shorts = presets["shorts-aggressive"]
    assert shorts.modules_config.shorts.max_clips_to_generate == 3


def test_invalid_preset_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"name": "bad"}), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_preset(path)
