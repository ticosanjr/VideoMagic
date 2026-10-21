# Module 07 — Vertical shorts

## Implementation status

Implemented: deterministic and LLM sentence selection, retake-aware conforming,
9:16/1:1/16:9 render, ASS captions, karaoke word timing, a live aspect-aware
caption preview in the rack, an optional source window, `videoflow shorts`, job/API/MCP execution, a telemetry
stage, and MP4 download. Not yet: face tracking and a per-Short editor.

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
| `min_clips` | 3 | 1–20 |
| `max_clips_to_generate` | 3 | 1–20 |
| `selection_mode` | `auto` | auto/llm/heuristic |
| `aspect_ratio` | `9:16` | 9:16 / 1:1 / 16:9 |
| `source_start_sec` | 0 | ≥ 0; sentences must start at or after it |
| `source_end_sec` | none | > start; sentences must end at or before it |
| `reframe_mode` | `center_crop_9_16` | center_crop_9_16 / auto_face_tracking_yolo |
| `burn_subtitles` | `true` | |
| `caption_style` | defaults | font, size, colors, outline, shadow, box, position, animation, word timing |
| `export_format` | `both` | fcpxml_timeline/standalone_mp4/both |

## Algorithm

1. Rank candidates by hook, impact, emotion, concrete numbers, contrast, and
   diversity. With an LLM, ask for the most important clips; otherwise use the
   heuristic. Both paths avoid overlapping windows.
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

## Captions and karaoke

Caption style is a full `CaptionStyle` model: font family, size, weight, italic,
uppercase, primary/highlight/outline colors, outline width, shadow color/offset/
opacity, background box color/opacity/padding, alignment, normalized position,
max width, animation, and word-timing fallback.

The renderer writes ASS and lets FFmpeg burn it. If the transcript has word
timings, it emits karaoke `\k`/`\kf` tags. Otherwise `word_timing=proportional`
distributes the sentence duration across words; `sentence` disables karaoke.
Text is escaped.

The rack preview is an approximate HTML rendering of the same style fields and
the selected aspect. It updates without rendering a video; the burned-in result
still comes from ASS. A per-Short trim/retitle editor is still planned.

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
