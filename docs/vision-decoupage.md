# Vision, decoupage, and corrections

## Eye-contact green labels

`vision.face_contact` samples the source and detects the largest centred face
with at least one visible eye. It writes:

- `vision/face-contact.json` — intervals, confidence, frame counts;
- `timeline_meta.json` markers named `Eye contact` in green `#00FF66`.

The marker end time is carried into FCPXML/XMEML exports, so the green label is
visible as a marker span in the NLE.

OpenCV is optional:

```bash
pip install 'videoflow[vision]'
```

Without it the step writes an explicit `available: false` report and the HILT
decoupage audit remains the manual path.

## Reference decoupage calibration

`decoupage.calibrate` reads a human-edited Premiere XMEML or FCPXML timeline,
extracts source intervals, and writes `decoupage/profile.json` and
`decoupage/profile.md`:

- reference cut count;
- kept ratio against the source duration;
- recommended retake strictness (`conservative`, `balanced`, `aggressive`);
- overlap with the current timeline when one is available.

`retakes.cull` with `use_profile: true` applies the recommended strictness.
The Full AI Editor asks for an optional reference XML after ingest and before
the retake pass.

## Frame-accurate speech map

`edit.drift` now writes `alignment/speech-map.json` with each sentence in
seconds and frames at the media frame rate, alongside the corrected transcript.
This is the input for graphics, lower thirds, and SFX timing.

## Entity corrections

`entities.apply` reads the answers from the HILT entity review and applies
`heard -> canonical` lines to the narrative entity manifest. It writes
`narrative/entities-corrected.json` and `.md`, keeping the before/after mapping
for audit. Corrections cover people, objects/locations, and metrics.

## Full AI Editor integration

```
ingest
  → baseline_files (human.files, optional)
  → decoupage.calibrate
  → vision.face_contact
  → vad / transcribe / drift / retakes
  → timeline
  → narrative / entities_review / entities.apply
  → decoupage_files / decoupage_review
```

## Entity extraction and transcription resume

`entities.extract` reads the context blocks and the edition script, resolves
single-word names from the script, adds quoted event/object phrases, and accepts
`known_entities` hints. The deterministic pass writes people, object/location/
event, and metric arrays with block time ranges; an LLM can refine the same
manifest without changing the schema.

`transcribe` writes a partial `transcribe.partial.json` after every segment,
keyed by the PCM digest. If the job stops mid-transcription, the next run loads
the partial sentences, trims the WAV tail, and resumes with an absolute sample
offset instead of redoing the entire recording. The partial file is removed on
success.


## Eye-contact backends

## Reframe tracking backends

`shorts.reframe` shares the same optional backend policy:

1. MediaPipe when `mediapipe` is installed and usable;
2. YOLO when `ultralytics` is installed and `yolo_model`/`VIDEOWFLOW_YOLO_MODEL`
   points to a local model;
3. OpenCV Haar;
4. motion centroid.

Recent MediaPipe wheels ship the Tasks API only, which needs a local face model.
Install `mediapipe-face-detector` from the Models catalog, or point
`mediapipe_model_path` / `VIDEOWFLOW_MEDIAPIPE_MODEL` at
`blaze_face_short_range.tflite` (or another Tasks face model). Older wheels with
the legacy Solutions API keep working without a model. `auto` skips MediaPipe
when no usable face model is configured.

Set `tracking_backend` in `shorts.reframe` or in `settings.vision`. `auto`
resolves in that order. The run writes `vision/tracking.json` with the requested
backend, the concrete backend, frames sampled, detections, and the fallback
reason. Configure `yolo_confidence`, `mediapipe_model_path`,
`tracking_smoothing`, and `tracking_sample_fps` in `settings.vision`. Install
with:

```bash
uv sync --extra vision
uv sync --extra tracking
```

`vision.face_contact` prefers MediaPipe Face Mesh when a MediaPipe build with
the legacy Solutions API is installed, then falls back to YOLO when `yolo_model`
points to a local face model, then to the OpenCV Haar path, and finally to the
manual HILT audit. Tasks-only MediaPipe wheels are skipped, because eye contact
needs Face Mesh landmarks. Set `backend` to
`mediapipe`, `yolo`, `opencv`, `auto`, or `none`. MediaPipe uses eye aspect
ratio and face centering; YOLO uses the largest detected face box and
`yolo_confidence`; OpenCV uses the largest face plus eye cascades.
