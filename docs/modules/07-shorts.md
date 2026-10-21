# Module 07 — Vertical shorts

## Implementation status

Implemented: deterministic and LLM sentence selection, retake-aware conforming,
9:16/1:1/16:9 render, ASS captions, karaoke word timing, a live aspect-aware
caption preview in the rack, an optional source window, `videoflow shorts`, job/API/MCP execution, a telemetry
stage, and MP4 download. The rack/API/MCP also expose a per-Short editor:
trim, retitle, change aspect, override caption fields, and re-render. Not yet:
face tracking.

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
| `prompt` | empty | topic or instruction for selection |
| `reprompt` | empty | refinement instruction |
| `prompt_mode` | `replace` | replace/refine |
| `hook_mode` | `off` | off/metadata/repeat/reorder |
| `remove_fillers` | `false` | cut filler words when word timings exist |
| `filler_words` | `hum, hmm, uh, um, ...` | configurable token list |
| `caption_style.censor_enabled` | `false` | mask profanity in ASS captions |
| `aspect_ratio` | `9:16` | 9:16 / 1:1 / 16:9 |
| `source_start_sec` | 0 | ≥ 0; sentences must start at or after it |
| `source_end_sec` | none | > start; sentences must end at or before it |
| `reframe_mode` | `center_crop_9_16` | center_crop_9_16 / auto_face_tracking_yolo |
| `burn_subtitles` | `true` | |
| `caption_style` | defaults | font, size, colors, outline, shadow, box, position, animation, word timing |
| `export_format` | `both` | fcpxml_timeline/standalone_mp4/both |

## Algorithm

1. Rank candidates by hook, impact, emotion, concrete numbers, contrast, and
   diversity. A prompt adds topic terms to the heuristic score and an explicit
   focus block to the LLM prompt. `prompt_mode=refine` passes the previous
   `shorts.json` selection as context. Both paths avoid overlapping windows.
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

## Auto hook and virality score

The selected clip carries `hook` (the highest-scoring sentence), its sentence id
and source range. `hook_mode=metadata` only annotates the clip;
`repeat` prepends the hook range; `reorder` moves it to the front and removes it
from its original position.

Every clip also carries a 0–100 `virality_score` and a transparent
`score_breakdown` (markers, question, exclamation, numbers, prompt, duration).
This is an explainable heuristic, not a platform-trained prediction.

## Fillers, censor, and metadata

When `remove_fillers` is on and the transcript has word timings, filler-word
intervals are subtracted from the Short pieces. Captions only render words that
remain inside the pieces. Caption profanity masking is a case-insensitive word
list with a configurable replacement.

`POST /api/v1/jobs/{job_id}/shorts/{index}/metadata` generates a deterministic
title, description, hashtags, and platform character limits for YouTube,
TikTok, Instagram, or LinkedIn. Results are stored under the Short's
`metadata.<platform>` entry.

## Intro and outro cards

PNG/JPEG assets from the image store can be prepended/appended to a Short with
configurable durations. Cards are normalized to the Short size, given silent
audio, and concatenated after captions, overlays, music, and voice-over.

## Reframing and tracking

`reframe_mode` can be `center_crop_9_16`, `motion_tracking`, `face_tracking`, or
the legacy `auto_face_tracking_yolo` label. Motion tracking decodes low-resolution
gray frames and uses the centroid of frame differences as the horizontal crop
focus. Face tracking uses OpenCV when installed and falls back to motion
tracking. The chosen focus is stored as `crop_focus_x`/`crop_focus_y` in
`shorts.json`.

## Brand templates

A `BrandTemplate` stores a caption style, overlay config, music config, and
intro/outro config under `<home>/brand_templates/`. Templates can be applied to
a job with `brand_template`, or applied in the rack to update the current form.

## Dubbing

`POST /api/v1/jobs/{job_id}/shorts/{index}/dub` sends the Short transcript to an
OpenAI-compatible chat endpoint for translation, then to the TTS endpoint, and
mixes the translated narration over the Short. The default original volume is
zero for dub-only playback; it is configurable. API keys stay in environment
variables.

## Voice-over

`POST /api/v1/jobs/{job_id}/shorts/{index}/voiceover` calls an
OpenAI-compatible `/audio/speech` endpoint, writes the MP3 under
`shorts/voiceover/`, lowers the original audio, and mixes the narration into a
new MP4. The API key is read from the configured secret name
(`VIDEOWFLOW_TTS_API_KEY` by default) and never enters project state.

## Background music

`MusicConfig` selects an uploaded track, volume, fades, and optional speech
ducking. The track is looped, trimmed to the Short duration, mixed with the
voice, and encoded as AAC after captions/overlays. NLE exports are unchanged.

## Watermark overlay

PNG/JPEG assets live under `<home>/assets/images`. `OverlayConfig` controls
position, margin, width ratio, and opacity. The overlay is composited after
captions on the final Short MP4, so it never affects the source or NLE exports.

## Audio enhancement

`AudioEnhanceConfig` controls optional FFmpeg processing for rendered Shorts:
high-pass, `afftdn` denoise, and `loudnorm`. The NLE exports keep the source
audio because the timeline is not baked. The CLI exposes `--audio-enhance`; API,
MCP, and the Shorts tab expose the full parameter set.

## Thumbnails

`POST /api/v1/jobs/{job_id}/shorts/{index}/thumbnail` extracts a frame, burns a
caption-style title with ASS, and stores a PNG under `shorts/thumbs/`. The
latest thumbnail is exposed as `thumbnail`; every generated variant is kept in
`thumbnails`.

## Captions and karaoke

Caption style is a full `CaptionStyle` model: font family, size, weight, italic,
uppercase, primary/highlight/outline colors, outline width, shadow color/offset/
opacity, background box color/opacity/padding, alignment, normalized position,
max width, animation, word-timing fallback, keyword highlight, emoji map, brand
vocabulary, and censor word list/replacement.

Keyword highlighting colors matching words in sentence captions. If the keyword
list is empty, the renderer auto-selects frequent content words. Emojis are
appended to matching words. Brand vocabulary rewrites ASR variants before
caption styling. TTF/OTF files can be stored under
`<home>/assets/fonts`; libass receives that directory through `fontsdir`, and
the internal family name should be used in `font_family`.

The renderer writes ASS and lets FFmpeg burn it. If the transcript has word
timings, it emits karaoke `\k`/`\kf` tags. Otherwise `word_timing=proportional`
distributes the sentence duration across words; `sentence` disables karaoke.
Text is escaped.

The rack preview is an approximate HTML rendering of the same style fields and
the selected aspect. It updates without rendering a video; the burned-in result
still comes from ASS. The per-Short editor writes a new file under
`shorts/edited/` and leaves the original render available.

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
