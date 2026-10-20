# User manual

This is the editor's guide. Installation belongs to the
[operator manual](operator.md).

> Status: the rack and the export buttons exist in the scaffold but are not wired
> to engines yet. This manual describes the product you run once the media passes
> land. Sections marked **Available now** work today.

## 1. The idea

VideoFlow does the tedious first pass, then hands you a real timeline:

- It keeps speech and cuts dead air.
- It removes failed takes, but never the last valid one.
- It overlaps audio at cuts so the edit does not sound abrupt.
- It adds tasteful punch-ins to hide jump cuts.
- It finds vertical moments.
- It writes files for Resolve, Premiere, and Kdenlive.

You still finish the edit in your NLE. VideoFlow never touches the source file.

## 2. First run

### Portable CLI (available now)

The model-free path is usable today:

```bash
videoflow run interview.mp4 -o interview-edit
```

It detects speech with FFmpeg, removes silence, applies J/L-cuts and punch-ins,
and writes `timeline.fcpxml`, `timeline.xml`, and `timeline.otio` into
`interview-edit/exports/`. `run.json` explains what happened. It does not
transcribe or remove retakes yet.

`videoflow demo -o demo` proves the whole chain on a generated clip.

`videoflow serve` exposes the same run as `POST /api/v1/jobs`, with progress at
`GET /api/v1/jobs/{id}` and `GET /api/v1/jobs/{id}/events`. The MCP tools
`videoflow_load_media`, `videoflow_run_pipeline`, `videoflow_get_job`, and
`videoflow_cancel_job` drive it from an agent.

### Rack UI (portable run)

1. Start `videoflow serve` and open `http://127.0.0.1:8765/`.
2. Enter the source path and an output project folder. **Default** derives the
   output from the source name.
3. Optionally enter an SRT transcript and enable **Cull retakes**.
4. Set the noise threshold and minimum silence, and choose J-cuts and punch-ins.
5. Press **Run pipeline**.

The page starts a job, shows the live stage and progress, and lists the three
artifacts as download links. Quick presets set the silence and cut options.
With an SRT, the inspector lists culled takes and any sentence the guard
restored.

The rack cards follow the active stage: green cached, blue running, yellow dirty,
gray bypassed/later, red failed. Cancel stops between stages.

The source/output paths must be inside the server's allowed roots
(`VIDEOWFLOW_ALLOWED_ROOTS`). The output folder gets `project_state.json`,
`run.json`, and `exports/`.

## 3. The eight cards

### 01 Ingest

Leave the defaults unless you have a reason.

- **Force CFR** fixes variable-frame-rate phone recordings. Keep it on.
- **Extract audio** is required for speech analysis.
- **Proxy** is preview-only. It never changes the analysis.

### 02 Voice detect

- **Threshold** higher means stricter about what counts as speech.
- **Minimum silence** is the shortest pause worth cutting. 400 ms is a good
  start; 700 ms for a lecture; 250 ms for shorts.
- **Pad before/after** protects consonants. Lower them only if cuts feel loose.
- **Handles** are hidden media used for J-cuts. Leave at 200 ms.

### 03 Transcribe

- **Model**: `small` on CPU, `medium` or `large-v3` if you have time or a GPU.
- **Language**: set it. `auto` is slower and can flip mid-file.
- **Device**: `cpu` unless CUDA is configured.
- **Compute type**: `int8` on CPU, `float16` on a supported GPU.
- **Whisper VAD**: leave off. Module 02 already does this.

### 04 Retakes

Today retakes come from an SRT file (the rack form does not expose this yet):

```bash
videoflow run interview.mp4 -o edit --transcript interview.srt --cull-retakes
```

- **Strictness**: conservative keeps more, aggressive cuts more.
- **Strategy**: `keep_last` is the safe default and the final-take guarantee.
  `keep_best` lets the model prefer an earlier scored take.
- **Context window**: 15 sentences. Raise it for long, repetitive passages.
- **Provider**: Ollama or any OpenAI-compatible endpoint, configured with
  `VIDEOWFLOW_LLM_BASE_URL`, `VIDEOWFLOW_LLM_MODEL`, and
  `VIDEOWFLOW_LLM_API_KEY`.

Without an LLM, exact repeated text is still culled. The report shows how many
sentences were cut and how many the guard restored. A restoration is not an
error; it is the safety rule working.

### 05 J/L-cuts

- **J-cuts** start the next audio early. On by default.
- **L-cuts** let the previous audio run under the next video. Off by default.
- **Offset** 100–500 ms. 200 ms is natural for speech.
- **Crossfade** 10–50 ms. 20 ms removes clicks without smearing consonants.
- **Handle check** skips an offset when there is not enough media. Keep it on.

### 06 Zooms

- **Alternate cuts** punches in on alternating clips.
- **Scale** 1.05–1.30. Above 1.20 is a style choice, not a fix.
- **Anchor** upper third is flattering for a face.
- **Progressive zoom** is a slow move across the take.
- **Face detect** is not available in v1; the UI explains and falls back.

### 07 Shorts

- **Duration** is the target after cuts, not before.
- **Count** caps the result.
- **Reframe** is center crop in v1.
- **Subtitles** burn karaoke-style captions into MP4 exports.
- **Export** chooses timeline clips, MP4 files, or both.

A clip that falls below the minimum after culling is dropped, not padded with a
bad take.

### 08 Export

- **FCPXML 1.9** for Resolve.
- **xmeml** for Premiere.
- **OTIO** for Kdenlive.
- **MP4** is a preview, not the master.

All enabled artifacts are written to `.videoflow/exports/`.

## 4. Reading the inspector

- Normal text: kept.
- Red strike-through: removed as a retake.
- Gray gap: removed silence.
- Badge **restored**: the model tried to cut the final take and the guard saved
  it.

Click a word to hear the source range. Click again to keep or discard it manually.
A manual decision wins over the model.

## 5. Rerunning cheaply

Change only a zoom value and press Run. Modules 01–05 stay cached; zooms and
export rerun. The card statuses tell you what will happen before you press it.

If you press **Run this block** on a card whose upstream is dirty, VideoFlow asks
whether to run the required modules. It does not silently do extra work.

## 6. Saving presets

**Save preset** stores your current module config and on/off flags under
`~/.videoflow/presets/`. It does not store media, secrets, or transcript. Share a
preset by copying the JSON file.

## 7. Exporting to an editor

See the [NLE import manual](nle-import.md). The short version:

- Resolve: File → Import → Timeline, choose `.fcpxml`.
- Premiere: File → Import, choose `.xml`.
- Kdenlive: File → Open, choose `.otio` (25.04+).

Check three things after import: audio is offset at a J-cut, the punch-in is
visible, and no join clicks.

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Card is yellow after a change | Expected. It will reprocess. |
| Run refuses with "upstream not cached" | Use the prompt to run the required modules. |
| Transcription is very slow | Switch to `small`/`int8`, enable cache, or configure CUDA. |
| Cuts clip the first consonant | Raise pad-before to 150–200 ms. |
| Cuts feel too tight | Raise minimum silence. |
| A word is missing from the export | Check a manual override and the inspector restoration badge. |
| Premiere will not open the file | Use the `.xml`, not the `.fcpxml`. |
| Shorts are shorter than expected | Culls reduce the window; that is by design. |

## 9. What VideoFlow will not do

Colour, mixing, multicam, b-roll, translation, or a final render for delivery.
It prepares the edit; you finish it.
