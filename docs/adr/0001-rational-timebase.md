# ADR-0001 — Rational time is authoritative

Status: accepted. Date: 2026-10-19.

## Context

The original brief stores `duration_sec`, `start`, and `end` as floats and
requires lip sync within one frame over 60 minutes. Float seconds cannot represent
29.97 fps exactly, and summing float frame durations accumulates error. The same
document uses `(fps, duration_sec)` for video and seconds for audio, which mixes
two grids.

## Decision

- Video positions are integer frame indices at `fps_num / fps_den`.
- Audio positions are integer sample indices at `audio_sample_rate`.
- Fades and offsets are integer samples.
- Seconds are derived only for display and prompts.
- Exporters emit reduced rational time strings.
- `Frame` and sample conversions use `Fraction` and explicit rounding.

## Consequences

- Every state field and every schema uses integers. A `duration_sec` field is
  removed; clients compute it.
- FCPXML gets exact `1001/30000s` values.
- A 60-minute NTSC recording is not an integer number of frames. The model derives
  frames from the real duration rather than assuming 108,000.
- Cut edges round outward to frames so an audio pad is never clipped.
- Slightly more code in the domain, and every consumer must agree on units. The
  schema and type names make that explicit.

## Alternatives rejected

- Float seconds: fails AC-02.
- Milliseconds: still cannot represent 1001/30000 exactly.
- Decimal seconds: exact in base 10 but not aligned to the frame grid, and it does
  not solve frame coverage.
- Timecode strings as storage: lossy for rates without drop-frame, and painful to
  compute with.
