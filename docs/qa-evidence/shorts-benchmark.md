# Scene intelligence and Dynamic Shorts benchmark

Generated: `2026-11-19T22:00:09+00:00`

| Check | Result | Metric |
| --- | --- | --- |
| geometry | PASS | `0.0` |
| face_tracking_60s | PASS | `0.0` |
| plan_sequence | PASS | `` |
| captions | PASS | `48` |
| scene_corpus | PASS | `1.0` |

## Thresholds

```json
{
  "scene_f1": 0.93,
  "detection_sec_per_hour": 45.0,
  "face_x_error_pct": 0.03,
  "caption_overlaps": 0,
  "truncated_words": 0,
  "safe_zone_bottom_px": 380,
  "safe_zone_right_px": 140,
  "fade_out_ms": 80,
  "gpu_render_60s_sec": 20.0
}
```

## Pending physical certification

`render_60s_sec` remains pending until a Windows RTX 3060 worker
measurement is recorded. The harness never claims that speedup.
