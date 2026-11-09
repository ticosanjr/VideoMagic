from __future__ import annotations

import json
from pathlib import Path

from videoflow.application.nle_extras import nle_extras_from_output


def test_motion_and_intro_become_overlay_entries(tmp_path: Path) -> None:
    motion = tmp_path / "motion"
    motion.mkdir()
    scene = motion / "SCENE-0001.mp4"
    scene.write_bytes(b"scene")
    intro = motion / "intro.mp4"
    intro.write_bytes(b"intro")
    (motion / "render-manifest.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "scene_id": "SCENE-0001",
                        "path": str(scene),
                        "start_sec": 3.0,
                        "duration_sec": 4.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (motion / "intro.json").write_text(
        json.dumps({"path": str(intro), "duration_sec": 8.0}), encoding="utf-8"
    )
    extras = nle_extras_from_output(tmp_path)
    names = {item.name for item in extras.broll}
    assert "SCENE-0001" in names
    assert "intro" in names
    assert next(item for item in extras.broll if item.name == "intro").start_sec == 0.0
