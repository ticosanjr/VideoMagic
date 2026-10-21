# Module 05 — J-cuts and L-cuts

## Implementation status

The deterministic builder is implemented in
`application/timeline_builder.py`: frame-quantised video, sample-aligned audio,
J/L boundary shifts with handle checks, and fade lengths in state. xmeml,
Kdenlive, and FCPXML/Resolve now emit audio fades (transition items, keyframed
volume filters, and `adjust-volume` ramps respectively). AC-01 remains xfail
until the three NLE imports are validated by hand.

## Purpose

Turn hard cuts into overlapping audio transitions without moving a video cut off
a frame boundary.

## Inputs

- Speech frame spans and sample pads from VAD.
- Retake culls and manual overrides.
- `JlCutsConfig`.

## Outputs

- `video_segments`: frame ranges on source and timeline.
- `audio_segments`: sample ranges on source and timeline.
- Fade lengths and curve per audio segment.

Video and audio share `clip_id` but may have different ranges. That difference is
the edit.

## Configuration

| Key | Default | Range |
| --- | --- | --- |
| `enable_j_cuts` | `true` | |
| `enable_l_cuts` | `false` | |
| `offset_ms` | 200 | 100–500 |
| `audio_crossfade_ms` | 20 | 10–50 |
| `fade_in_ms` | 20 | 0–1000 |
| `fade_out_ms` | 20 | 0–1000 |
| `fade_curve` | `logarithmic` | linear/logarithmic |
| `handle_check` | `true` | |

## Algorithm

1. Sort kept intervals by source start.
2. For each, take the padded sample span and the covering frame span.
3. Trim overlap against the previous clip so no source range repeats.
4. Add a handle before and after, bounded by neighbouring cuts and the media.
5. Create a video segment at the frame span.
6. Create an audio segment at the sample span.
7. For a J-cut, start the next clip's audio `offset_ms` before its video, but only
   if the handle allows it.
8. For an L-cut, extend the previous audio `offset_ms` under the next video.
9. Place a logarithmic fade of `audio_crossfade_ms` on both sides of each join.
10. Pack timeline positions contiguously: video from frame zero, audio from
    sample zero.
11. Validate no overlaps, no inverted ranges, and no audio offset without a
    handle.

## Handle rule

A J-cut consumes audio from the next clip before its video starts. That audio
must exist in the source. If the previous trim consumed the handle, the offset
would overlap a word. With `handle_check`, skip the offset instead of risking a
clipped word. Record the skip in the module summary.

## Fade

`audio_crossfade_ms` × `audio_sample_rate / 1000`, rounded to the nearest sample.
The curve is logarithmic by default because a linear ramp at a discontinuities is
audible. The crossfade must be shorter than both adjacent clips.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| Zero kept clips | Fail; do not export an empty timeline |
| Fade longer than a clip | Clamp to half the clip, record a warning |
| Offset with no handle | Skip the J-cut when handle check is on |
| Overlapping timeline | Fail; do not silently pack |
| Float time | Rejected by the model validator |

## Tests

| Id | Case |
| --- | --- |
| T-05-01 | One clip produces one video and one audio segment |
| T-05-02 | J-cut starts audio before video and keeps the video edge on a frame |
| T-05-03 | L-cut extends previous audio |
| T-05-04 | Missing handle skips the offset |
| T-05-05 | Fade is 960 samples at 48 kHz for 20 ms |
| T-05-06 | Audio and video timeline lengths match within one frame |
| T-05-07 | Zero clips fails |
| T-05-08 | Every join has a fade |

AC: 01, 02.
