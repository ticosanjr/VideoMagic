# Rack UI specification

Stack: SvelteKit 2, Svelte 5, Tailwind CSS 4, TypeScript. English strings only.

The scaffold renders the rack shell with static sample data. It does not call the
API. The live behavior below is the contract for the UI pass.

## 1. Layout

```
┌──────────────────────────────────────────────────────────────┐
│ VideoFlow     [drop media]  [preset ▾]  [Run pipeline]       │
│ Project: interview       ████████████░░  transcribe  62%     │
├──────────────────────────────────────────────────────────────┤
│ 01 Ingest        ● cached     [Run this block]        ▸      │
│ 02 Voice detect  ● cached     [Run this block]        ▸      │
│ 03 Transcribe    ◐ running    [Run this block]        ▾      │
│    model   [small ▾]   language [pt ▾]  device [cpu ▾]       │
│ 04 Retakes       ○ dirty      [Run this block]        ▸      │
│ …                                                            │
├──────────────────────────────────────────────────────────────┤
│ Inspector: transcript, kept / cut / retake, word overrides    │
└──────────────────────────────────────────────────────────────┘
```

The rack is the page. There is no dashboard, wizard, or modal pipeline. The
editor's mental model is a chain of inserts, so the UI is a vertical chain.

## 2. Header

- **Media drop zone**: accepts one video. Calls media registration, then shows
  duration, resolution, rational frame rate.
- **Global progress**: active module and a per-module bar. No invented ETA. If an
  ETA exists, it is derived from measured module time.
- **Preset menu**: load, save as, delete. Applying a preset marks affected cards
  dirty. It does not start a run.
- **Run pipeline**: starts the enabled, non-cached modules. Disabled while a job
  runs.
- **Cancel**: replaces Run during a job.

## 3. Module card

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

## 4. Inspector

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

## 5. States

### Empty

No media: the rack shows the eight cards in `bypassed` with a call to drop a file.
Run is disabled.

### Loading

A skeleton per card. No layout shift when the config arrives.

### Error

A card-level error keeps the rest of the rack usable. A project-level error
(path denied, corrupt state) replaces the rack with a recovery panel.

### Disconnected

If SSE drops, the header shows **Reconnecting**. The UI keeps the last state and
polls job status every 5 s until the stream returns.

## 6. Accessibility

- Every control has a label, not just a placeholder.
- Status is text plus color, never color alone.
- The accordion is keyboard operable and announces expanded state.
- Focus is visible on dark and light themes.
- The inspector does not rely on color for keep/discard; it uses strike-through
  and an icon.
- Reduced motion disables the running pulse.

## 7. Implementation notes

- API base is `/api/v1`; the dev server proxies to `127.0.0.1:8765`.
- State fetching uses a typed client generated from the JSON Schemas, not ad hoc
  `any`.
- The card config form is derived from `modules_config` in `ProjectState`.
- SSE is `EventSource`; no polling fallback for progress except after a drop.
- Toasts are for transient success. Persistent failures belong in the card.

## 8. Out of scope

Timeline scrubbing, video preview compositing, subtitle styling preview, and
multi-project tabs. The UI edits decisions, not pixels.
