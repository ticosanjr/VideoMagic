# Motion, audio, and intro

## Motion codegen

`motion.codegen` turns the unit storyboard, style guide, and approved asset
assignments into `motion/scenes.json`. Each scene has:

- `scene_id`, `unit_id`, timing, dimensions, fps;
- background/accent/text palette;
- optional asset layer (`image` or `video`);
- title, lower-third, or panel layers with start/duration.

The model never writes executable code. The scene graph is data.

## Motion render

`motion.render` renders each scene with the bundled FFmpeg backend:

- solid palette background;
- approved asset scaled/cropped to frame;
- lower-third drawbox;
- title/narration text with a fade;
- fade in/out;
- H.264 MP4.

It writes `motion/rendered/SCENE-*.mp4` and
`motion/render-manifest.json`. The NLE export reads the manifest and places the
clips on the overlay track. Remotion can be selected as a future backend but is
not bundled; the step falls back to FFmpeg with a warning.

## Procedural music and Foley

`audio.compose` synthesizes a copyright-free bed and stems with numpy. No
third-party recording is used. It writes `audio/music/music-bed.wav` plus pad,
bass, and pulse stems.

`sfx.synthesize` generates Foley cues:

- paper turn;
- keyboard click with a -4 dB notch at 3.5 kHz;
- marker underline;
- whoosh;
- riser;
- impact.

Cues are placed at rendered scene starts, or at a 30-second cadence when no
motion scenes exist. The plan is `audio/sfx-plan.json`.

`audio.mix` mixes the dialogue master, music bed, and Foley cues with FFmpeg,
writes `audio/final.wav`, and mirrors it to `audio/master.wav` so the NLE export
uses the final mix. `audio.qa` then measures the final master.

## Intro compiler

`intro.compile` selects approved assets and builds a fast-cut montage, or a
title card when no asset is available. It writes `motion/intro.mp4` and
`motion/intro.json`; the NLE export places it at the start of the overlay track.

## Full AI Editor checkpoints

```
assets.assign
  → motion.codegen
  → motion.render
  → sfx.synthesize
audio.master → audio.compose → audio.mix → audio.qa
intro.compile
  → sample_review (HILT)
```

The sample review includes `motion/render-manifest.json`, `motion/intro.json`,
and `audio/qa.json`.
