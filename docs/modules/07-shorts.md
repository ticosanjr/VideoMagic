# Module 07 — Vertical shorts

## Implementation status

Implemented: deterministic and LLM sentence selection, retake-aware conforming,
1080x1920 H.264/AAC render, ASS captions, and `videoflow shorts`. Not yet:
face tracking, karaoke word-level captions, and API/MCP exposure.

## Purpose

Find self-contained moments in the transcript and turn them into vertical clips.

## Inputs

- Transcript and sentence ids.
- Retake culls.
- `ShortsConfig`.

## Outputs

- `vertical_clips`: source sample windows with title, crop focus, reframe mode.
- Optional `exports/shorts/*.mp4` with burned captions.
- Optional timeline ranges for NLE import.

## Configuration

| Key | Default | Range |
| --- | --- | --- |
| `target_duration_min_sec` | 30 | ≥ 1 |
| `target_duration_max_sec` | 60 | ≥ min |
| `max_clips_to_generate` | 3 | 1–20 |
| `reframe_mode` | `center_crop_9_16` | center_crop_9_16 / auto_face_tracking_yolo |
| `burn_subtitles` | `true` | |
| `subtitles_preset` | `tiktok_bold` | tiktok_bold/minimalist_box/highlight_word |
| `export_format` | `both` | fcpxml_timeline/standalone_mp4/both |

## Algorithm

1. Send indexed transcript windows to the LLM with the duration window and a
   request for a hook, development, and conclusion.
2. Accept only windows whose edges align with sentence boundaries.
3. Convert source samples to the kept timeline; intersect with the cull set.
4. Measure the conformed duration.
5. Drop a clip below the minimum after conform. Do not pad with a discarded take.
6. Trim a clip above the maximum at a sentence edge.
7. Cap at `max_clips_to_generate`, keeping the model's ranking.
8. Reframe `center_crop_9_16` around `crop_focus_x` (default center). The YOLO mode
   is an interface only in v1.
9. Render captions from word timings when requested.
10. Export per `export_format`.

## Conformed duration

A source window of 45 s can become 28 s after culls. The minimum applies after
conform, because that is what a viewer experiences. The module reports dropped
clips and why; the UI shows the warning.

## Captions

- `tiktok_bold`: heavy sans, white with black outline, word-level highlight.
- `minimalist_box`: lower third, small, solid background.
- `highlight_word`: one active word in accent color.

The renderer writes ASS and lets FFmpeg burn it. Text is escaped.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| Model returns a window outside the transcript | Drop, warn |
| Window crosses a discarded take | Conform, then re-check duration |
| All windows too short | Return zero clips with a warning; not a failure |
| FFmpeg absent | Timeline clips still export; MP4 is skipped with a warning |
| YOLO requested | Fall back to center crop, warn |

## Tests

| Id | Case |
| --- | --- |
| T-07-01 | Three valid windows yield three clips |
| T-07-02 | A 30 s window with 5 s culled becomes 25 s and is dropped |
| T-07-03 | A window is clipped to the maximum at a sentence edge |
| T-07-04 | Captions use source word timings |
| T-07-05 | YOLO falls back to center |
| T-07-06 | `max_clips_to_generate` is respected |
| T-07-07 | Timeline-only export writes no MP4 |

AC: 04, 06.
