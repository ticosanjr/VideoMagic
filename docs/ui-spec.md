# Rack UI specification

Stack: SvelteKit 2, Svelte 5, Tailwind CSS 4, TypeScript. English strings only.

0.39.0 keeps the full telemetry rack from 0.13 and adds detailed configuration
for zoom bounds, audio fades, Shorts count/selection, and caption/karaoke style,
plus a live 9:16 caption preview and audio fades in all three NLE exports.
The setup card shows source metadata, an output suggestion, starting-point
cards, an explicit “Also render vertical shorts” control, inline validation, and
a clear primary action. Per-block progress, start/finish timestamps, duration,
status icons, per-block and global log drawers, recent jobs, artifact downloads,
and typed errors remain.

Module cards render configuration from `modules.ts` field metadata. Implemented
controls are bound to the job request; future controls are disabled and marked
`later`. Transcribe accepts an SRT, a local Faster-Whisper or whisper.cpp engine,
or an OpenAI-compatible ASR endpoint; SRT wins, and an ASR base URL takes
precedence over the local engines. Shorts runs when enabled and a transcript is
present, with rendered MP4s in the run summary.

The inspector reads `GET /api/v1/jobs/{id}/state`, lists transcript sentences,
and exposes Keep/Discard overrides plus an Apply overrides action. Applying
starts a new job with the same configuration and the override set.

The rest of this document is the contract for later passes: real per-block runs,
persisted presets, and word-level inspector controls.

## 1. Layout

```
┌──────────────────────────────────────────────────────────────┐
│ VideoFlow      0.39.0   FFmpeg ready          [Global log]   │
├──────────────────────────────────────────────────────────────┤
│ New project                                      [Run]       │
│  01 Source video        [Choose / Change]                    │
│     clip.mp4 · 12:04 · 1920×1080 · 30 fps · 48 kHz           │
│  02 Output project      [Choose / Create]                    │
│     /videos/clip-videoflow                                   │
│  03 Transcript (SRT)    [Choose]                             │
│  Starting point: YouTube · Lecture · Shorts · Custom         │
│  ▸ Advanced paths and local models                           │
├──────────────────────────────────────────────────────────────┤
│ 01 Ingest        ● cached     [Run this block]        ▸      │
│ 02 Voice detect  ● cached     [Run this block]        ▸      │
│ 03 Transcribe    ◐ running    [Run this block]        ▾      │
│ 04 Retakes       ○ dirty      [Run this block]        ▸      │
│ …                                                            │
├──────────────────────────────────────────────────────────────┤
│ Inspector: transcript, kept / cut / retake, word overrides    │
└──────────────────────────────────────────────────────────────┘
```

The rack is the page. There is no dashboard or wizard. The filesystem picker is
a modal utility, not a pipeline step. The editor's mental model is a chain of
inserts, so the UI remains a vertical chain.

## 2. Header and project setup

- **Source picker**: opens the local filesystem browser, filters media
  extensions, then calls `/api/v1/media/probe` and shows duration, resolution,
  frame rate, audio rate, and size. It never uploads the file.
- **Output picker**: browses directories, shows which are writable, and can
  create a new folder. Selecting a source suggests `<source-stem>-videoflow`.
- **Transcript picker**: optional `.srt` file, filtered in the same browser.
- **URL import**: a public URL field imports through yt-dlp when external services are enabled.
- **Starting point**: YouTube, Lecture, and Main + Shorts cards. The Shorts
  add-on keeps the main project and adds vertical MP4s; manual changes switch
  the badge to Custom.
- **Detailed controls**: zoom min/max, fade in/out and curve, Shorts target and
  minimum count, selection mode, and every caption/karaoke style field are
  editable. Color fields use a native color picker plus a hex field.
- **Advanced paths**: a collapsed fallback for typed paths plus Faster-Whisper
  and whisper.cpp model pickers.
- **Global progress**: active module and a per-module bar. No invented ETA. If an
  ETA exists, it is derived from measured module time.
- **Run pipeline**: starts the enabled, non-cached modules. Disabled while a job
  runs or while a required source/output is missing, the zoom window is invalid,
  or Shorts are enabled without a transcript/transcription path.
- **Cancel**: replaces Run during a job.

### Path picker

The picker is a modal dialog with:

- quick-access chips for every allowlisted root;
- breadcrumbs and an Up action that never escapes the containing root;
- a search field for the current folder;
- a hidden-file toggle;
- rows with folder/file icon, name, size, modified date, and symlink marker;
- single-click selection for files, click-to-enter for folders;
- a New folder field and Create action in directory mode;
- a footer with the selected absolute path and a disabled Select action until a
  valid selection exists;
- loading skeletons, empty states, and typed errors;
- Escape to close, focus trapping, and visible focus states.

Short-form controls are one continuous form: zoom bounds, fade timings, Shorts
target/minimum/selection, prompt/reprompt, aspect ratio, source window, and caption
font/colors/box/shadow/position. Duration buttons set common min/max pairs. The
caption preview follows the selected aspect and shows the configured font,
colors, outline, shadow, box, alignment, and position. The per-Short editor has
Clip, Captions, and Metadata tabs. Saving a clip/caption edit writes a fresh
render under `shorts/edited/`; the Metadata tab generates platform title,
description, hashtags, a PNG thumbnail with preview/download, a TTS voice-over,
translation dubbing, multimodal analysis, and webhook scheduling.

The picker never offers a parent above the allowlisted root. If a symlink points
outside the roots it is omitted. Network shares and unlisted disks require an
operator change to `VIDEOWFLOW_ALLOWED_ROOTS`.

## 3. Tabs

The rack opens on **Recipes**, the visual DAG editor. The manual tabs remain so
the pipeline does not read as one long wall of controls:

| Tab | Contents |
| --- | --- |
| Recipes | Svelte Flow DAG editor, step palette, parameter JSON, validation, save/download, run and live job progress |
| Speech | Ingest, voice detection, transcription, retakes |
| Edit | J/L cuts, fades, zooms, framing |
| Shorts | Target/minimum, prompt/reprompt, auto hook, audio-energy + scene boosts, reframing/tracking, filler cuts, audio enhancement, watermark, intro/outro, music, brand templates, censor, keyword/emoji/brand styling, custom fonts, metadata, duration presets, aspect ratio, source window, captions, score, preview |
| Studio | AI analysis, timeline, keyframes, tracks, transitions |
| Export | NLE targets and FCPXML dialect |
| Models | On-demand local model downloads |
| Services | Local service discovery, restart, stop, cleanup, logs |
| Providers | Capability manifest and external-service opt-in/blocking |

The Recipes tab uses the full content width and hides the legacy New project
and run-summary panels. A **Batch** modal runs the current recipe over a folder,
with item-level progress and cancellation. The legacy Export card includes an
**MP4** target. The step palette is a filterable popover, the step
inspector is a right-side overlay that opens on node click, and recipe settings
plus step/recipe JSON use modal editors. This keeps the canvas wide while the
controls remain one click away.

Each node reports its latest execution state: **cached**, **executed**,
**running**, or **failed**. The inspector also exposes **Run to here**, which
runs only that node and its dependency closure. The Config modal contains the
**Reuse existing step checkpoints** switch. After a successful run, **Compare**
opens a modal with the previous successful run for the same output and recipe:
duration, cached/executed counts, warnings, and per-step status/timing.

The manual tabs keep the current run summary and history sidebar visible. Module
counts are shown per tab. The Providers tab is not a pipeline module; it reads
`GET /api/v1/capabilities` and explains available, blocked, partial, and planned
features.

## 4. Module card

Anatomy:

1. Index and name.
2. Enable switch.
3. Status badge.
4. `Run this block`.
5. Accordion body with the controls from the module spec.

Status:

| Badge | Meaning | Color |
| --- | --- | --- |
| `cached` | Identity matches | green |
| `dirty` | Parameters or upstream changed | yellow |
| `running` | Executing | blue, animated |
| `bypassed` | Switched off | gray |
| `failed` | Last run failed | red |
| `blocked` | Upstream not ready | orange |

Clicking `Run this block` when the API returns `upstream_dirty` opens an inline
panel: "Transcribe is not cached. Run it first?" with two buttons: **Run required
modules** and **Cancel**. It never silently ignores the error.

Controls are generated from the config schema. Numeric fields show their range
and units. A change marks the card dirty immediately, but does not persist until
the debounce (400 ms) completes.

## 5. Inspector

Sections:

- **Transcript**: sentences in source order. Kept text is normal. A retake cull is
  struck through in red. Removed silence is a gray gap marker.
- **Words**: a click selects a word. A second click opens Keep / Discard. The
  audio slice plays from the API.
- **Restorations**: a small badge on a sentence the guard saved. Tooltip: "The
  model discarded this final take; the guard restored it."
- **Warnings**: word timing below confidence threshold, a cut near a word edge,
  or a shorts clip dropped after conform.

Overrides are optimistic in the UI, then reconciled with the response. A failed
write reverts the row and shows the error.

## 6. States

### Empty

No media: the rack shows the eight cards in `bypassed` with a call to choose a
source file. Run is disabled until source and output are present.

### Loading

A skeleton per card. No layout shift when the config arrives.

### Error

A card-level error keeps the rest of the rack usable. A project-level error
(path denied, corrupt state) replaces the rack with a recovery panel.

### Disconnected

If SSE drops, the header shows **Reconnecting**. The UI keeps the last state and
polls job status every 5 s until the stream returns.

## 7. Accessibility

- Every control has a label, not just a placeholder.
- Status is text plus color, never color alone.
- The accordion is keyboard operable and announces expanded state.
- Focus is visible on dark and light themes.
- The inspector does not rely on color for keep/discard; it uses strike-through
  and an icon.
- Reduced motion disables the running pulse.

## 8. Implementation notes

- API base is `/api/v1`; the dev server proxies to `127.0.0.1:8765`.
- The path picker uses `/api/v1/fs/list`, `/api/v1/fs/mkdir`, and
  `/api/v1/media/probe`; it never uploads media.
- `PathPicker.svelte` owns modal state and focus; `paths.ts` owns pure path
  helpers so Windows and POSIX suggestions are unit-tested.
- Source metadata is advisory. A failed probe shows a warning but does not block
  the run; the worker still probes the file.
- State fetching uses a typed client generated from the JSON Schemas, not ad hoc
  `any`.
- The card config form is derived from `modules_config` in `ProjectState`.
- SSE is `EventSource`; no polling fallback for progress except after a drop.
- Toasts are for transient success. Persistent failures belong in the card.

## 9. Out of scope

Timeline scrubbing, video preview compositing, and multi-project tabs. The
caption preview is style-only; the Short editor edits clips and captions, not
individual video frames.
