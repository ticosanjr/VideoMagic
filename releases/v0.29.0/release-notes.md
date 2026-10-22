# VideoFlow 0.29.0

This release adds clip transitions.

## Transitions

- `VideoSegment.transition_out` stores a `Transition`:
  - `crossfade` or `fade_to_black`;
  - duration in frames;
  - optional audio crossfade.
- `edit.timeline` accepts `transition_frames` and `transition_type`.
- **FCPXML** emits a `transition` element between clips.
- **XMEML** emits a video `transitionitem` with Cross Dissolve/Fade to Black.
- **MP4** uses `xfade` + `acrossfade` for crossfades and video/audio fades for
  fade-to-black.

Crossfades overlap adjacent clips, so the MP4 is shorter by the transition
duration. Fade-to-black keeps the timeline length.

## Validation

- 411 Python tests passed; 14 UI tests passed.
- FCPXML and XMEML tests parse the generated documents and find the transition
  element.
- MP4 filter-graph tests cover `xfade` and fade-to-black.
- A real two-cut recipe rendered an MP4 with a crossfade and produced FCPXML
  and XMEML transition elements.
- The 0.29.0 AppImage ran the same recipe through its CLI.

## Notes

Kdenlive still does not apply clip transforms or per-cut transitions. That is
the remaining NLE parity gap.

## Artifacts

- `videoflow-0.29.0-linux-x86_64` — SHA-256 `1eb169146be62c7d7542c72f4d832215116273a0c4b8d41673b6bab062dbab06`
- `VideoFlow-0.29.0-x86_64.AppImage` — SHA-256 `2f6bf305ce6b9dc9935c9f03fe3a1239fd5940d42c7698b039fff31139afaf09`

The build is lean; speech weights are downloaded from the Models tab. Windows
PE is not included because no Windows/Wine build host was available.
