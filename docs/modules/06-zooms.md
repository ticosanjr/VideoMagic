# Module 06 — Framing and zooms

## Purpose

Mask jump cuts and add visual rhythm without manual keyframes. Zoom is metadata,
not a render.

## Inputs

- `video_segments` from the cut engine.
- `ZoomsConfig`.

## Outputs

- `transform` on each affected video segment: scale, position, type, anchor, and
  optional pan.

## Configuration

| Key | Default | Range |
| --- | --- | --- |
| `mode` | `alternate_cuts` | alternate_cuts/topic_change/manual_rules |
| `punch_in_scale` | 1.15 | 1.05–1.30 |
| `anchor_point` | `upper_third` | center/upper_third/face_detect |
| `progressive_zoom` | `false` | |
| `pan_direction` | `none` | none/left_to_right/right_to_left |

## Algorithm

### alternate_cuts

1. Sort segments by timeline order.
2. Segment 0 is neutral (`scale=1.0`).
3. Alternate punch-in and neutral for subsequent segments.
4. A single segment stays neutral unless `manual_rules` says otherwise.

### topic_change

Place a punch-in at a large semantic break, derived from sentence transitions or
chapter markers. v1 may approximate this with a configurable minimum gap; the
exact semantic rule is an open enhancement, not a hidden heuristic.

### manual_rules

Apply the configured rule list in order. A rule may target a clip id or a range.
An empty rule list is neutral.

### progressive_zoom

For a punched segment, replace the static scale with two keyframes: 1.0 at the
start, `punch_in_scale` at the end, or the reverse. The interpolation is linear in
the NLE.

### pan

Move `pos_x` across the segment in normalized frame units. This is for a 4K source
in a 1080p timeline; in a same-resolution timeline it would crop content.

### face_detect

Not implemented in v1. Selecting it is a validation warning, not a crash. The
exporter writes `anchor="center"` and the run records that face tracking was
requested but unavailable. The UI disables the option with an explanation.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| Scale out of range | Validation error |
| No segments | No-op |
| Manual rule targets a missing clip | Fail with the clip id |
| Face detect requested | Fall back to center, warn |

## Cache

Changing only `punch_in_scale` invalidates zooms and export. It does not invalidate
modules 01–05. This is AC-05.

## Tests

| Id | Case |
| --- | --- |
| T-06-01 | Three segments alternate neutral/punch/neutral |
| T-06-02 | Scale is clamped by validation |
| T-06-03 | Progressive zoom creates two keyframes |
| T-06-04 | Pan shifts position monotonically |
| T-06-05 | Face detect falls back with a warning |
| T-06-06 | A zoom-only change does not dirty ingest–jl_cuts |

AC: 05, 06.
