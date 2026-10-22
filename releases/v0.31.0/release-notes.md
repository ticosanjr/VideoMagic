# VideoFlow 0.31.0

This release adds the content layer: speaker turns, local B-roll, split-screen
Shorts, and local Piper TTS.

## Speaker turns and colored captions

- `audio.diarize` assigns heuristic speaker ids using pauses between sentences.
- `Sentence.speaker` persists the id in the project state.
- `CaptionStyle.speaker_colors` colors each speaker in the ASS output.
- This is pause-based labeling, not model-based diarization.

## Local B-roll

- `broll.plan` scans a local asset directory, matches filenames to selected
  Shorts, and writes `broll.json`.
- `shorts.render` applies the B-roll plan as a full-frame cutaway.
- No stock-video service is contacted; assets are operator-provided.

## Split-screen Shorts

`shorts.render` accepts `split_screen: true` and renders a two-panel vertical
frame using the left and right halves of the source.

## Local Piper TTS

The voice-over route accepts `provider: "piper"` with a local binary and voice
model path. The existing OpenAI-compatible TTS route remains available.

## Validation

- 417 Python tests passed; 14 UI tests passed.
- A real Shorts recipe with diarization, B-roll, split-screen, and captions ran
  to success and produced:
  - an MP4 at 1080x1920;
  - an ASS file with two speaker color overrides;
  - `broll.json` with a local asset plan.
- The 0.31.0 AppImage ran the same recipe through its CLI.

## Artifacts

- `videoflow-0.31.0-linux-x86_64` — SHA-256 `6e9e7f4ad23ae002fc2c47ec5e75addf9f7953bbe11acbe59b12154b26947302`
- `VideoFlow-0.31.0-x86_64.AppImage` — SHA-256 `547a962221248c8d4dac417d03844682531b0f58501533cf05e7a1e604df805b`

The build is lean; speech weights are downloaded from the Models tab. Windows
PE is produced by the GitHub Actions Windows workflow, not on this Linux host.
