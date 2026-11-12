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

`vision.face_contact` prefers MediaPipe Face Mesh when `mediapipe` is installed,
then falls back to the OpenCV Haar path, and finally to the manual HILT audit.
Set `backend` to `mediapipe`, `opencv`, `auto`, or `none`. MediaPipe uses eye
aspect ratio and face centering; OpenCV uses the largest face plus eye cascades.
