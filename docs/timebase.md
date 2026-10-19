# Timebase

## 1. Why floats are banned

`0.1 + 0.2` is not `0.3`, and 29.97 frames per second is not `0.0333667`
seconds. Sum 108,000 frame durations as floats and the timeline drifts. The v1
acceptance gate allows one frame of error over an hour. That is only achievable
with exact arithmetic.

Rules:

1. Video positions are integer frame indices.
2. Audio positions are integer sample indices.
3. Fades, pads, and J-cut offsets are integer samples.
4. Seconds are a derived property for display and prompts.
5. Export times are reduced fractions, formatted as `num/den s`.

`Fraction` is used for conversions and for FCPXML strings. Integers are used for
storage and identities.

## 2. Frame rate and duration

```
frame_duration = fps_den / fps_num
frames_to_seconds(n) = n * fps_den / fps_num
seconds_to_frames(t) = t * fps_num / fps_den
```

Examples:

| Declared rate | `fps_num` | `fps_den` | One frame |
| --- | --- | --- | --- |
| 23.976 | 24000 | 1001 | `1001/24000s` |
| 25 | 25 | 1 | `1/25s` |
| 29.97 | 30000 | 1001 | `1001/30000s` |
| 30 | 30 | 1 | `1/30s` |
| 50 | 50 | 1 | `1/50s` |
| 59.94 | 60000 | 1001 | `1001/60000s` |

Reducible fractions are reduced by gcd, so `60/2` becomes `30/1`. NTSC rates are
already reduced and keep their declared form.

## 3. Frames and samples

```
frame_start_sample(f) = floor(f * sample_rate * fps_den / fps_num)
```

The first sample belongs to the frame. The sample that lands exactly on a frame
edge belongs to the next frame.

To cover a sample interval `[start, end)`:

```
first_frame = floor(start * fps_num / (sample_rate * fps_den))
last_frame  = ceil(end   * fps_num / (sample_rate * fps_den))
frame_span  = [first_frame, last_frame)
```

This span always covers the whole audio interval. A pad applied before a
consonant stays inside the video clip.

## 4. Pads, handles, and cuts

Order matters:

1. Detect speech in samples.
2. Apply `speech_pad_before_ms` and `speech_pad_after_ms`, clamped to `[0, duration]`.
3. Expand the padded interval to covering frames.
4. Use the frame span as the candidate video cut.
5. Keep `keep_handles_ms` of extra media around the cut. Handles are not played;
   they enable J/L offset and fade room.
6. If `handle_check` is on and the handle is shorter than `offset_ms`, skip that
   J-cut rather than overlap a word.

`padded_end == padded_start` after clamping is an error, not an empty clip. It
means the pad calculation and the media bounds disagree; the run fails loudly.

## 5. Rounding policy

| Use | Policy | Why |
| --- | --- | --- |
| Speech start to frame | floor | Include the first frame that contains speech |
| Speech end to frame | ceil | Include the last frame that contains speech |
| J-cut audio offset | nearest sample | Sub-millisecond precision is inaudible |
| Fade length | nearest sample | Same |
| Display seconds | exact fraction, then decimal | Never the reverse |

Rounding half up is used for `NEAREST`. The difference only matters at exact
half-sample boundaries, which the tests pin.

## 6. FCPXML representation

FCPXML accepts rational time:

```xml
<sequence duration="3600s" format="r1" tcStart="0s" tcFormat="NDF">
  <spine>
    <asset-clip offset="0s" duration="1001/30s" start="0s" />
  </spine>
</sequence>
```

`format_frame_time(30)` on a 29.97 timeline returns `1001/1001s`? No: it returns
`30030/30000s`, which reduces to `1001/1000s`. Use the `frameDuration` attribute
from the format resource and rational offsets; never emit a rounded millisecond
string. The exporter must not use float formatting.

## 7. 60-minute proof

For 30 fps:

```
3,600 s * 30 = 108,000 frames
108,000 * (1/30) = 3,600 s exactly
```

For 29.97:

```
3,600 s * 30000/1001 = 107,892.107... frames
```

A 60-minute NTSC recording is not an integer number of frames. The pipeline works
in frame counts derived from the real media duration; it never assumes that an
hour is 108,000 frames. Drift cannot accumulate because no step re-derives time
from a float.

The automated proof is `test_sixty_minutes_of_30fps_has_no_float_drift` and the
Hypothesis round-trip tests. The manual proof is the long-import lip-sync check.

## 8. API surface

`Timebase` exposes:

- `frame_duration`, `frames_to_seconds`, `seconds_to_frames`
- `samples_to_seconds`, `seconds_to_samples`
- `milliseconds_to_samples`
- `frame_start_sample`, `frame_to_sample`, `sample_to_frame`
- `expand_samples_to_frames`
- `apply_pads`
- `format_frame_time`

`FrameSpan(start, end)` is inclusive-start, exclusive-end. `PaddedSpan` carries
the clamped samples and the covering frames.
