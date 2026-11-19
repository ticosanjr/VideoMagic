from __future__ import annotations

from pathlib import Path

from PIL import Image

from videoflow.application.overlay_geometry import PixelBox, collisions
from videoflow.domain.state import MediaInfo, OverlayClip, ProjectState

RATE = 48_000


def _state(tmp_path: Path) -> tuple[ProjectState, Path]:
    image = tmp_path / "card.png"
    rgba = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    for x in range(10, 21):
        for y in range(10, 21):
            rgba.putpixel((x, y), (255, 0, 0, 255))
    rgba.save(image)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    media = MediaInfo(
        source_path=str(source),
        duration_frames=30,
        fps_num=30,
        fps_den=1,
        width=200,
        height=200,
        audio_sample_rate=RATE,
    )
    return (
        ProjectState(
            media_info=media,
            overlays=[
                OverlayClip(
                    overlay_id="card",
                    path=str(image),
                    start_frame=0,
                    duration_frames=30,
                    anchor="top_left",
                    width_ratio=0.5,
                )
            ],
        ),
        image,
    )


def test_visual_collision_ignores_transparent_pixels(tmp_path: Path) -> None:
    state, _ = _state(tmp_path)
    caption = PixelBox(x=80, y=80, width=10, height=10, z=40)
    assert collisions(state, 200, 200, caption=caption, mode="visual") == []
    assert collisions(state, 200, 200, caption=caption, mode="rectangle")


def test_visual_collision_finds_the_opaque_area(tmp_path: Path) -> None:
    state, _ = _state(tmp_path)
    caption = PixelBox(x=8, y=8, width=8, height=8, z=40)
    visual = collisions(state, 200, 200, caption=caption, mode="visual")
    assert visual
    assert visual[0]["kind"] == "caption_overlap"
    assert visual[0]["overlap_px"] > 0
