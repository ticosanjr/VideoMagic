# VideoFlow 0.32.0

This release closes the Kdenlive gap and exposes the 0.29–0.31 features in the
recipe UI.

## Kdenlive

- Video entries now receive an MLT `affine` filter with `transition.rect`.
- Static transforms and keyframed zooms are written into the project.
- Clip transitions add affine opacity keyframes plus volume ramps, so Kdenlive
  shows a fade at each cut.
- Audio fades include the transition duration.

Kdenlive is not installed on this build host, so the project was validated by
XML inspection, not by opening it in Kdenlive. The emitted transition is an
opacity/volume fade, not a separately validated exact cross-dissolve.

## Recipe UI

- Inspector quick controls for:
  - transition frames and type;
  - progressive zoom;
  - speaker-turn method and pause;
  - local B-roll directory, count, and cutaway duration;
  - split-screen and B-roll application;
  - caption speaker colors.
- New persisted run-history browser with a Compare action.
- Short editor now exposes the Piper provider, binary, and voice-model path.

## Fix

Crossfades combined with progressive zoom failed because `xfade` rejected the
input timebase. Video chains now append `settb=AVTB`, and a regression test
covers the combination. The two-cut recipe now renders an MP4, FCPXML, XMEML,
and Kdenlive project successfully.

## Validation

- 419 Python tests passed; 14 UI tests passed.
- The 0.32.0 AppImage rendered a two-cut recipe with crossfade plus progressive
  zoom to MP4, FCPXML, XMEML, and Kdenlive.
- The Kdenlive XML contains four affine `transition.rect` properties.

## Artifacts

- `videoflow-0.32.0-linux-x86_64` — SHA-256 `0750230013f77d06aeda1ff23b9a3c2bb4c63603c1116ef5475a814e09e93563`
- `VideoFlow-0.32.0-x86_64.AppImage` — SHA-256 `01e386ce605a07aebd074e7dd0c61452b70078fdff7841a9cb66ae16d6061d84`
