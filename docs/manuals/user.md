# User manual

This is the editor's guide. Installation belongs to the
[operator manual](operator.md).

> Status: the portable CLI, REST API, recipe studio, canvas timeline, and MCP
> surface run real jobs in 0.70.0. Local Faster-Whisper quality transcription is
> available with a whisper.cpp fallback. The UI browses local files and folders
> through the server allowlist; it does not upload media.

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

Public URLs can be imported from the Source card when external services are
enabled. The downloaded file lands in the VideoFlow downloads folder and then
follows the normal local probe.

### Portable CLI (available now)

The portable path is usable today:

```bash
videoflow run interview.mp4 -o interview-edit
```

It detects speech with Silero VAD when the model is available and falls back to
FFmpeg, removes silence, applies J/L-cuts and punch-ins, and writes
`timeline.fcpxml`, `timeline.xml`, and `timeline.kdenlive` into
`interview-edit/exports/`. `run.json` reports the selected `vad_engine` and what
happened. Add `--transcribe` for local Faster-Whisper with a whisper.cpp
fallback, or `--transcript` with `--cull-retakes` for retake removal.

`videoflow demo -o demo` proves the whole chain on a generated clip.

`videoflow serve` exposes the same run as `POST /api/v1/jobs`, with progress at
`GET /api/v1/jobs/{id}` and `GET /api/v1/jobs/{id}/events`. The MCP tools
`videoflow_load_media`, `videoflow_run_pipeline`, `videoflow_get_job`, and
`videoflow_cancel_job` drive it from an agent.

### Rack UI (portable run)

1. Start `videoflow serve` and open `http://127.0.0.1:8765/`.
2. Press **Choose source video**. The picker starts in an allowed root and shows
   folders, media files, sizes, and modified dates. Selecting a file also probes
   it for duration, resolution, frame rate, and audio rate.
3. The output folder is suggested next to the source. Keep it, or press
   **Choose output folder** to browse and create a new folder with **Create**.
4. Optionally choose an SRT transcript. The picker filters `.srt` files.
5. Pick a starting point: YouTube, Lecture, or Shorts. Tune individual modules
   below; any change switches the badge to Custom.
6. Set the noise threshold and minimum silence, and choose J-cuts and punch-ins.
7. Press **Run pipeline**.

The page starts a job, shows the live stage and progress, and lists the three
artifacts as download links. Quick presets set the silence and cut options.
With an SRT, the inspector lists every sentence: Keep/Discard sets a manual
override, and **Apply overrides** starts a new job with that decision. Guard
restorations are shown separately.

Recipe steps follow the active stage: green cached, blue running, yellow dirty,
gray bypassed/later, red failed. Cancel stops between stages.

The source/output paths must be inside the server's allowed roots
(`VIDEOWFLOW_ALLOWED_ROOTS`). The picker shows those roots as quick-access
buttons. A path outside them returns `path_not_allowed`; symlinks are resolved
before the check. The output folder gets `project_state.json`, `run.json`, and
`exports/`. Advanced users can still paste paths under **Advanced paths and
local models**.

## 3. The eight cards

### 01 Ingest

Leave the defaults unless you have a reason.

- **Force CFR** fixes variable-frame-rate phone recordings. Keep it on.
- **Extract audio** is required for speech analysis.
- **Proxy** is preview-only. It never changes the analysis.

### 02 Voice detect

- **Engine**: `Auto` prefers Silero VAD and falls back to FFmpeg. `Silero`
  requires the bundled model and ONNX Runtime. `FFmpeg` is the portable fallback.
- **Speech probability**: Silero threshold. Higher is stricter. 0.5 is a good
  start; raise it for noisy rooms.
- **Minimum silence** is the shortest pause worth cutting. 400 ms is a good
  start; 700 ms for a lecture; 250 ms for shorts.
- **Pad before/after** protects consonants. Lower them only if cuts feel loose.
- **Handles** are hidden media used for J-cuts. Leave at 200 ms.

### 03 Transcribe

- **Local engine**: `Auto` uses Faster-Whisper when its package and model are
  available, then falls back to whisper.cpp. Pick one explicitly to require it.
- **Model size**: `small` on CPU, `medium` or `large-v3` if you have time or a
  GPU. The release bundles `small`; larger models need a local model directory.
- **Faster-Whisper model**: optional CTranslate2 directory. Leave empty for the
  bundled model.
- **Language**: set it. `auto` is slower and can flip mid-file.
- **Device**: `cpu` unless CUDA is configured.
- **Compute type**: `int8` on CPU, `float16` on a supported GPU.
- **Whisper VAD**: leave off. Module 02 already does this. Turning it on filters
  the full WAV; it does not make the pipeline pre-slice audio.

### 04 Retakes

Today retakes come from a transcript supplied to the recipe:

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

Shorts are additive. The main project is always exported; enable
**Also render vertical shorts** in the setup card, or use:

```bash
videoflow run interview.mp4 -o edit --transcript interview.srt --shorts   --shorts-count 3 --shorts-min-count 3 --shorts-min-sec 30 --shorts-max-sec 60
```

The standalone `videoflow shorts` command remains available for a separate
vertical-only output.

- **Target/minimum count**: the default is 3; the pipeline warns if the material
  cannot produce the configured minimum.
- **Selection**: `auto` uses the LLM when an endpoint is configured, then the
  heuristic; `llm` requires ranking; `heuristic` ranks hook, impact, numbers,
  contrast, and diversity without a model.
- **Prompt**: describe the topic you want, for example “the pricing and margin
  discussion”. The heuristic boosts matching terms and the LLM receives it as
  an explicit focus.
- **Reprompt**: set prompt mode to **Refine previous selection** and describe the
  adjustment. The previous `shorts.json` is used as context; without one, it
  falls back to replacement.
- **Auto hook**: choose `metadata` to annotate the hook, `repeat` to play it at
  the start, or `reorder` to move it to the first seconds. The hook is the
  highest-scoring sentence inside the selected clip.
- **Virality score**: a 0–100 explainable score with a breakdown. It is a
  heuristic aid, not a guarantee or a platform-trained prediction.
- **Fillers**: enable **Remove filler words** to subtract configured tokens when
  word timings exist.
- **Censor**: enable **Censor profanity** and edit the comma-separated word list.
- **Keyword highlight**: color configured words, or leave the list empty to
  auto-select frequent content words.
- **Emojis**: map words to emojis with `word=emoji` pairs.
- **Brand vocabulary**: rewrite ASR variants with `wrong=Preferred` pairs.
- **Custom fonts**: upload a TTF/OTF in the Shorts tab. The upload reports the
  internal family name; click it to put that name in Caption font.
- **Metadata**: open a Short's **Metadata** tab, choose platform/tone, and
  generate title, description, hashtags, and character limits.
- **Thumbnail**: choose a frame time in the Metadata tab and generate a PNG with
  the caption-style title overlay.
- **Audio enhancement**: optional high-pass, FFT denoise, and loudness
  normalization for rendered Shorts. NLE exports keep the source audio.
- **Watermark**: upload a PNG/JPEG, choose position/margin/size/opacity, and
  enable the overlay for rendered Shorts.
- **Music**: upload an audio track, set volume/fades, and optionally duck it under
  speech.
- **Voice-over**: in the Metadata tab, enter narration text plus a TTS base URL,
  model, and voice. External services must be enabled in Providers.
- **Intro/outro**: pick uploaded images and durations. Cards are added after the
  Short render, with silent audio.
- **Dubbing**: enter the target language and LLM/TTS endpoints. The transcript is
  translated, synthesized, and mixed over the Short. External services must be
  enabled.
- **Brand templates**: save the current caption/overlay/music/intro/outro
  settings under a name and apply them later in one click.
- **Publishing**: add a webhook target, choose platform/tone, and schedule the
  Short. The queue posts metadata and the local asset path when due.
- **Multimodal analysis**: analyze one Short for audio-energy/emotion proxy,
  motion coverage, and optional face count/focus.
- **Reframe mode**: center crop, motion tracking, or optional face tracking.
  Motion tracking shifts the crop toward the strongest frame-difference region;
  face tracking falls back to motion when OpenCV is unavailable.
- **Audio-energy boost**: gives extra score to clips overlapping loud audio
  peaks. The Short reports how many peaks it covers.
- **Scene-change boost**: gives extra score to clips around visual cuts detected
  by FFmpeg; the Short reports `scene_changes`.
- **Project templates / config**: save reusable run configuration, apply it, and
  export/import a versioned non-secret JSON envelope.
- **Duration** is checked after retake culling. The Shorts tab also has
  `0–1`, `1–3`, `3–5`, and `5–10` minute presets.
- **Aspect ratio** is `9:16`, `1:1`, or `16:9`. ASS and FFmpeg use the same
  selected size.
- **Source window** limits Short selection to a start/end range. `0` at the end
  means “until the end of the source”.
- **Reframe** is center crop in v1.
- **Karaoke captions**: font family, size, weight, italic, uppercase, text/
  highlight/outline colors, outline width, shadow color/offset/opacity, box
  color/opacity/padding, alignment, position, max width, animation, and word
  timing are configurable in the recipe, API, and MCP.
- **Caption preview**: the Shorts tab shows a live approximation in the selected
  aspect. The burned-in result still comes from ASS.
- **Edit a Short**: use **Edit** in the run summary to trim, retitle, change
  the aspect, and override font size/colors/box opacity. The server writes a new
  MP4 under `shorts/edited/`; the original file stays available.
- **Stop words**: a long source can still yield fewer than the minimum; the UI
  and `run.json` report the warning.

A clip that falls below the minimum after culling is dropped, not padded with a
bad take.

### 08 Export

- **FCPXML 1.9** for Resolve.
- **xmeml version 4** for Premiere.
- **Native `.kdenlive` MLT XML** for Kdenlive.
- **MP4** is a preview, not the master.
- All three NLE timelines include audio fades at cut edges.

All enabled artifacts are written to `.videoflow/exports/`.

## 4. Workspace tabs

The studio has six tabs:

- **Recipes** — build, validate, run, save, and template recipe DAGs. This is
  the only execution path.
- **Assets** — scan folders, search, tag, license, download, and remove local
  media.
- **Timeline** — edit the canonical `project_state.json` on a canvas, preview
  with titles/color/audio filters, and approve deliverables.
- **Automation** — once/interval schedules and watch folders.
- **Models** — download speech/vision models with progress and cancellation.
- **Services** — inspect, restart, or stop local VideoFlow processes.
- **Providers** — persist provider endpoints, defaults, and fallback chains.

## 5. Timeline editing

Select a clip to expose red trim handles. Drag the clip body to move it; edges
snap to the playhead, other clips, captions, and zero. The toolbar provides
undo/redo, split at the playhead, delete, ripple delete, zoom, fit, and a snap
toggle. Keyboard shortcuts are Space, `S`, Delete, Shift+Delete, and
Ctrl/Cmd+Z.

The video preview and waveform stay synced with the playhead. **Render preview**
builds a 540p proxy in the background with progress and cancel; it applies the
title plan, color/LUT grade, and audio-master filters. The playhead timecode is
editable.

Every edit increments `revision` and writes `timeline_history.json`. Rendered
artifacts are not silently reused; re-run the export or recipe after editing.

Captions can be edited in the right-hand list. The clip inspector edits
transition type/length, scale, position, and audio fade in/out. Shorts expose
the full Short editor: reframe, captions, metadata, thumbnail, voice-over,
dubbing, analysis, and publishing. Deliverables show the review checklist,
approval state, and thumbnail A/B variants.

B-roll plans are listed per Short. Approve or reject entries, reorder them, and
save. The renderer consumes only approved entries in that order.

## 6. Providers and models

Providers are stored in `providers.json`; secrets remain in environment
variables. Pick a default per capability and list fallback IDs. The resolve
endpoint returns the default followed by fallbacks, and the LLM job runner uses
the first configured provider when no explicit base URL is set.

Model downloads run in the background with progress, cancellation, checksum
verification, and disk usage. Weights are optional and live under the
VideoFlow home.

## 7. Automation

Create a schedule in the Automation tab:

- **Once** runs the recipe at the next scheduler tick.
- **Interval** runs every N seconds after the previous run.
- **Watch folder** queues a new job for each matching file not seen before.

Each item records status, last run, errors, and seen files. The scheduler polls
every 20 seconds and can be disabled with `VIDEOWFLOW_RECIPE_SCHEDULER=0`.

## 8. Exporting to an editor

See the [NLE import manual](nle-import.md). The short version:

- Resolve: File → Import → Timeline, choose `.fcpxml`.
- Premiere: File → Import, choose `.xml`.
- Kdenlive: File → Open, choose `.kdenlive` (23.04+).

Check three things after import: audio is offset at a J-cut, the punch-in is
visible, and no join clicks.

## 9. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Error banner stays visible | Read the code/message, fix the field, then dismiss. |
| Timeline will not split | Put the playhead strictly inside the selected clip. |
| Preview is missing | Press **Render preview** or run an export that writes MP4. |
| Transcription is very slow | Switch to `small`/`int8`, enable cache, or configure CUDA. |
| Cuts clip the first consonant | Raise pad-before to 150–200 ms. |
| Cuts feel too tight | Raise minimum silence. |
| Premiere will not open the file | Use the `.xml`, not the `.fcpxml`. |
| Shorts are shorter than expected | Culls reduce the window; that is by design. |

## 10. What VideoFlow will not do

Distribution, code signing, macOS packaging, final color grading, and multicam
switching are out of scope. It prepares the edit; you finish it in your NLE.
