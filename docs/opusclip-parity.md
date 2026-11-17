# OpusClip parity

VideoFlow implements the OpusClip workflow natively instead of running
ComfyUI graphs. The three recipes in `recipes/opusclip_*.json` map the
supplied ComfyUI workflows onto the step registry.

## Feature matrix

| ID | Area | Status | VideoFlow implementation |
| --- | --- | --- | --- |
| F01 | Speech cleanup and voice isolation | Partial | `audio.master`, `audio.vad`, `audio.isolate`, `edit.timeline` filler cuts. Source separation is optional and falls back to the mastered audio. |
| F02 | Transcription and alignment | Complete | `transcribe` word timestamps, `audio.diarize`, `edit.drift`, and optional `alignment.forced` (WhisperX, faster-whisper fallback). `language="auto"` persists the detected language and confidence in state, metadata, and `transcript/language.json`. |
| F03 | AI clipping and virality | Partial | `shorts.select`, `shorts.score` with heuristic/LLM/hybrid modes, `narrative.beats`, explainable 0–100 score, `virality_threshold`, arc labels, and LLM justification. |
| F04 | Reframe and face tracking | Complete | `shorts.reframe` resolves `auto` to MediaPipe, YOLO (local model), OpenCV Haar, or motion, smooths/interpolates focus, and writes `vision/tracking.json` with the used backend and fallback reason. |
| F05 | Kinetic captions | Mostly complete | `shorts.captions` karaoke, keyword highlight, emoji, speaker colors, `caption_presets`, ASS renderer. |
| F06 | AI B-roll | Partial | `broll.generate`, `broll.plan`, `assets.*`, `assets.match`, overlay/PiP render. |
| F07 | Timeline and NLE export | Mostly complete | `edit.timeline`, `export.nle` FCPXML/XMEML/Kdenlive/EDL, `export.video`, `nle.qa`, `delivery.package`, `metadata.pack` social sidecar. |

## Recipes

### `opusclip_auto_shorts`

Long-form cleanup, diarization, retakes, narrative beats, viral Shorts,
explainable scoring, dynamic reframe, kinetic captions, render, and NLE
export.

### `opusclip_auto_broll`

The Shorts flow plus `broll.generate` and `broll.plan`. Generated images are
written to the asset library and to `assets/licenses.json`; local assets can be
used instead.

### `opusclip_nle_bridge`

Long-form timeline, chapters, NLE exports, NLE QA, Shorts metadata,
thumbnails, and a delivery package.

## Optional backends

| Capability | Backend | Fallback |
| --- | --- | --- |
| Voice isolation | RNNoise, DeepFilterNet, Demucs | mastered audio |
| Face tracking | MediaPipe, YOLO local model, OpenCV Haar | motion centroid |
| Forced alignment | WhisperX | faster-whisper |
| Language detection | ASR-reported | stopword/langdetect text hint |
| Synthetic B-roll | OpenAI-compatible image endpoint (FLUX/SD/ComfyUI bridge) | skip with warning |
| Diarization | pyannote | pause heuristic |

## ComfyUI

The supplied JSON uses ComfyUI `class_type` nodes and cannot execute in
VideoFlow. Use the native recipes above. A future `comfyui/` bridge can expose
VideoFlow recipes as ComfyUI custom nodes, but it is not required for parity.
