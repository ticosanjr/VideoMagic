# Scene manifest

`scenes_manifest.json` is the compact Module A output. It never embeds images;
keyframes are absolute paths and are read on demand.

## Required

- `video_id`, `source_topology`, `resolution`, `fps_num`, `fps_den`.
- One entry per scene with `scene_id` (`SC_0001`), sample and second bounds.
- `transition_source`: `VISUAL_CUT` or `DECUPAGEM_JUMP`.
- `layout_type`: `TALKING_HEAD`, `SCREEN_SHARE_PIP`, `SCREEN_SHARE_FULL`,
  `DUAL_CANVAS_OBS`, or `BROLL_OR_FOOTAGE`.
- `face_count`, `face_bbox_norm`, `face_area_ratio`, `edge_density`,
  `sharpness_laplacian`.
- `keyframe_path` (544 px JPEG).
- `editing_hints`: `LONG_STATIC_SHOT`, `SCENE_TYPE_SWITCH`,
  `PROTECT_FROM_BROLL`, `LOW_SHARPNESS_WARNING`, `SAFE_FOR_BROLL`.

## Rules

- Scene ids are unique and ordered by `start_sample`.
- Boundaries are continuous from `0` to the source duration. A visual cut that
  would create a scene shorter than `min_scene_len_sec` is merged into the next
  scene instead of leaving a gap.
- `end_sample > start_sample`; seconds are display fields only.
- `PROTECT_FROM_BROLL` is mandatory for `SCREEN_SHARE_PIP`,
  `SCREEN_SHARE_FULL`, and `DUAL_CANVAS_OBS` with screen activity.
- Re-analysis with different Short layouts must reuse the SHA-256 cache.
