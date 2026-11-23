# Shorts batch schema

`vf_shorts` validates every clip with `extra="forbid"`. Unknown keys are
rejected instead of silently ignored.

## Required

- `start_sec`, `end_sec`
- `time_basis`: `timeline` (default) or `source`
- `source_id` when the project has more than one source

## Optional

- `title`, `style_id`
- `aspect_ratio`: `9:16`, `4:5`, `1:1`, `3:4`, `2:3`, `16:9`
- `fps`: 15–60; default 30; output is CFR
- `layout` / `layout_mode`: `auto`, `cutout`, `rounded_window`, `full_screen`,
  `split_top_visual`, `headline_card`, `fullscreen_punchin`, `pip_bottom_right`,
  `split_screen_50_50`
- `intro_path`, `intro_duration_sec`, `outro_path`, `outro_duration_sec`
- `crop_keyframes`, `face_center_lock`, `caption_preset`
- `music_path`, `overlay_path`, `visual_path`, `broll_path`,
  `second_source_path`
- `min_sec`, `max_sec`
- `thought_boundary`, `thought_boundary_max_adjust_sec`
- `start_pad_ms`, `end_pad_ms`, `max_internal_silence_ms`, `crossfade_ms`

## Duration

After `shorts.tighten` and `thought_boundary`, the expected duration includes
intro/outro. The rendered file must match within one frame. A clip below
`min_sec` or above `max_sec` is rejected; it is never silently shortened.

## Intro assets

`intro_path` must exist. PNG/JPG cards loop for `intro_duration_sec`; MP4/MOV
cards are trimmed to that duration. ASS captions are shifted by exactly one
intro duration.
