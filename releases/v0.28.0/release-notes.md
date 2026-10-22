# VideoFlow 0.28.0

This release adds progressive zoom keyframes to the timeline and three exporters.

## Keyframes

- `Transform` now carries normalized `TransformKeyframe` entries.
- `progressive_zoom` generates two smooth keyframes from minimum scale to the
  punch-in scale for alternating clips.
- The project-state schema includes the new keyframe model.

## Exporters

- **FCPXML:** `adjust-transform` emits a keyframed `scale` parameter with
  clip-relative rational times.
- **XMEML:** Basic Motion emits scale `keyframe` entries with clip-relative
  frame positions.
- **Direct MP4:** clips with keyframes use FFmpeg `zoompan` while keeping the
  source output dimensions.

Kdenlive does not apply clip transforms yet, so it does not represent these
keyframes.

## Validation

- 408 Python tests passed; 14 UI tests passed.
- FCPXML and XMEML tests parse the generated XML and assert two scale keyframes.
- A real two-cut source with `progressive_zoom` rendered an MP4 successfully;
  `ffprobe` reported H.264/AAC at the source dimensions.
- The 0.28.0 AppImage ran the same recipe through its CLI and wrote both the MP4
  and FCPXML.
- The AppImage server started without a terminal, and a second launch reused it.

## Not in this release

Transitions between clips remain the next editing pass.

## Artifacts

- `videoflow-0.28.0-linux-x86_64` — SHA-256 `3791163b4db82ac503224473afd1b2cb4322ebfdc88f529a7057fa3351f3c621`
- `VideoFlow-0.28.0-x86_64.AppImage` — SHA-256 `ae219695a90749b81204204ca8edff2a4b2f92383e96d08dc6f98570239e1e03`

The build is lean; speech weights are downloaded from the Models tab. Windows
PE is not included because no Windows/Wine build host was available.
