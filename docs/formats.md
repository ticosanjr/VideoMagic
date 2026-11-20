# Format presets

Format presets define output geometry and delivery constraints:

```json
{
  "format_id": "vertical_9_16",
  "name": "YouTube Shorts / Reels 9:16",
  "aspect_ratio": "9:16",
  "width": 1080,
  "height": 1920,
  "fps": 30,
  "safe_zones": {"bottom_px": 380, "right_px": 140},
  "caption_preset": "youtube_bold_yellow",
  "platforms": ["youtube_shorts", "reels", "tiktok"],
  "export_targets": ["mp4_short", "fcpxml"]
}
```

Seeds: `vertical_9_16`, `feed_4_5`, `square_1_1`, `landscape_16_9`.
Custom presets live under `$VIDEOWFLOW_HOME/formats/*.json`.

- UI: Setup → Formats. Preview safe zones, create, edit, duplicate, delete.
- MCP: `vf_format(action="list|get|save|delete|duplicate")`.
- Built-ins cannot be deleted or overwritten; duplicate them to customize.
