# High-level compositors

The core MCP exposes four compositors for effects that used to require manual
FFmpeg filter graphs. They write normal `OverlayClip` entries, so previews,
layout packing, QA, MP4 delivery, and NLE export see the same layers.

## `vf_depth_composite`

```text
vf_depth_composite(
    project_id="p1",
    text_or_asset="Nvidia no Brasil",
    start_sec=2.0,
    end_sec=4.0,
    style_props={"palette": ["#101114", "#ffcc4d"], "font": "Inter"},
)
```

- trims only the requested range from the primary source;
- runs background removal on that sub-range, never on the whole video;
- renders the text/asset with alpha;
- appends `z=10` (graphic) and `z=20` (matted presenter).

Pass an existing image or video path as `text_or_asset` to use a prepared
asset. Text is rendered through the Hyperframes backend and cached by content,
canvas, palette, and duration.

## `vf_pip`

```text
vf_pip(
    project_id="p1",
    overlay_asset="/media/screen.mp4",
    start_sec=8.0,
    end_sec=20.0,
    anchor="bottom_right",
    width_ratio=0.28,
)
```

The asset is scaled to an even-sized box, masked with a cached rounded PNG, and
encoded as WebM with alpha. The overlay is placed at `z=25` with 32 px margins.
Images and videos are both accepted.

## `vf_parallax`

```text
vf_parallax(
    project_id="p1",
    image_path="/media/photo.jpg",
    start_sec=4.0,
    end_sec=9.0,
    bg_scale=1.04,
    fg_scale=1.12,
    rotate_y_deg=3.0,
)
```

Background removal produces the subject PNG. The compositor builds two layers:
a softly blurred, slowly scaling background and a faster subject with opposite
lateral drift and a small `rotateY`. The result is a `z=10` floating card.

## `vf_style_preview`

```text
vf_style_preview(project_id="p1", style_id="sr-viral-depth-split", duration_sec=5)
```

Renders a draft card using the style palette, preferred font, layout label,
hook text, and caption preset. Use it to compare styles before applying one to
the timeline. The output follows the style aspect ratio (`9:16`, `4:5`, `16:9`,
and so on) and falls back to the project canvas.

## Requirements and failures

- `vf_depth_composite` and `vf_parallax` need the vision server's background
  removal backend.
- Hyperframes rendering needs the bundled Chromium path (`VF_CHROME_BIN` or the
  Playwright install).
- `vf_pip` needs Pillow for the rounded mask.
- Missing backends return a structured `videoflow_error` with a fix hint; no
  partial overlays are written.
