# Changelog

All notable changes are recorded here. Format follows Keep a Changelog; versions
follow semantic versioning once the project reaches 1.0.

## [2.40.0] - 2026-11-02

### Added

- Multi-selection batch editing now includes scale and X/Y position.
- Reset transform applies scale 1 and centered position to every selected clip.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.39.0] - 2026-11-02

### Added

- Multi-selection inspector now edits transition type, duration, fade-in, and
  fade-out for every selected clip in one action.
- Batch style application keeps the existing copy/paste and deactivate actions.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.38.0] - 2026-11-02

### Added

- Fixed timeline track headers that stay visible while the canvas scrolls.
- Previous/next marker navigation from the transport and `Alt+Left/Right`.
- Frame thumbnails with source-time labels while hovering the Recut canvas.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.37.0] - 2026-11-02

### Added

- Timeline hover thumbnails with a debounced frame preview and source time.
- Waveforms in the Recut audio lane, using the same peaks as the Normal canvas.
- Multi-selection inspector with Fit selection, Deactivate selected, and Paste
  style actions.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.36.0] - 2026-11-02

### Added

- In/out marks with `I`/`O`, a visible range overlay, and Clear marks.
- Fit selection (`Shift+F`) alongside Fit all.
- Copy/paste clip style for transition, scale, position, fades, and transition
  length, including multi-selection.
- The shortcuts reference now lists timeline in/out, activation, and fit
  selection commands.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.35.0] - 2026-11-02

### Added

- One preview surface for Normal and Recut, driven by the same transport.
- Timeline cursor seeks the preview; play/pause, segment navigation, speed, and
  click-to-seek work across live and rendered preview modes.
- Waveform fallback and signal filtering keep the audio track visible even when
  peaks are missing or all-zero.
- Zoom down to 2 px/s with adaptive ruler steps; horizontal wheel/Shift+wheel
  scrolls, vertical wheel zooms.
- Quick `X` toggle for active/inactive segments and an inactive-segment list in
  Normal view.
- **Use in recipe** from a timeline snapshot opens the builder with a configured
  `timeline.load` node.
- Activity, notifications, command palette, and shortcuts are portalled above
  the workspace navigation.

### Fixed

- Recipes with wired inputs but missing `needs` are repaired automatically,
  fixing `source timeline must run earlier` errors.
- Legacy `export.nle` configurations with `mp4` migrate to timeline-only targets.
- Activity/notification overlays no longer render behind the Produce/Edit/Runs/
  Library/Setup bar.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.34.0] - 2026-11-02

### Added

- **Separate timeline and video export nodes.** `export.nle` now writes only
  Resolve/FCPXML, Premiere/XMEML, and Kdenlive timelines. New `export.video`
  renders the direct video file.
- `export.video` presets: `ultrafast` (default, libx264 ultrafast/CRF 30),
  `fast`, `balanced`, and `quality`, plus configurable output folder and
  filename.
- All built-in recipes with a timeline now end with both `export.nle` and
  `export.video`.
- Quick node enable/disable from the node header and the inspector. Disabled
  nodes are omitted from the recipe run without deleting their configuration.

### Notes

- Full-tree coverage remains above the 95% gate.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.33.1] - 2026-11-02

### Added

- **Browser-safe live source proxy.** The timeline reports a `live_source`
  status. Compatible H.264/AAC sources stream directly; other codecs or sources
  above 1080p are transcoded once to a cached 1280px H.264/AAC proxy.
- `POST /jobs/{id}/live-source`, `GET /jobs/{id}/live-source/status`, and
  `GET /jobs/{id}/live-source/file` build, report, and serve the proxy with
  Range support.
- The Recut player shows a fixed-height preparation state, then switches to the
  proxy URL when ready; failure falls back to the rendered preview.

### Notes

- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.33.0] - 2026-11-02

### Added

- **Editor-first timeline layout.** The timeline is pinned above a fixed-height
  preview and scrollable inspector, so selecting clips or showing messages no
  longer moves it.
- Icon transport with start/end, previous/next segment, play/pause, one-frame
  and one-second seeks, and 1.0x–3.0x playback speed in 0.5x steps.
- Click-to-seek on the ruler, empty tracks, clips, and Recut blocks. The playhead
  can be scrubbed, and the mouse wheel over the timeline zooms instead of
  scrolling the page.
- Timeline shortcuts for playback, navigation, cutting, zoom, speed, save, and
  open, documented in the shortcuts modal.
- **Saved timeline versions.** Save, list, load, and delete named snapshots.
  Loading increments revision and records undo.
- **`timeline.load` recipe step** loads a saved timeline and exposes its state
  and media ports for export or render without rerunning analysis.

### Fixed

- Live playback no longer captures the wrong video element after a seek, and an
  audio failure no longer prevents the video clock from running.
- Playback speed is applied to both crossfade layers and the separate audio
  elements.

### Notes

- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.32.2] - 2026-11-02

### Added

- **Stop all** in the Activity drawer, backed by
  `POST /api/v1/jobs/cancel_all`. It cancels every queued, running, paused, or
  approval-waiting job and immediately drains the queue.
- Bulk test coverage for stopping running and queued jobs together.

### Notes

- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.32.1] - 2026-11-02

### Fixed

- Portable jobs now receive the same cancelable FFmpeg adapter as recipes, so
  force stop also kills their running FFmpeg process.
- Portable export reports per-target progress and honours cancellation.
- MP4 is always written after the NLE targets, even in a custom recipe that
  lists it first.

### Notes

- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.32.0] - 2026-11-02

### Fixed

- **Recut no longer blocks on an MP4 render inside `export.nle`.** The Recut
  recipes write Resolve, Premiere, and Kdenlive timelines only. Render the MP4
  from the Edit tab when the cut is final.
- **The Edit tab opens as soon as `edit.timeline` finishes.** `project_state.json`
  is published atomically after the timeline step, and running jobs with
  `timeline_ready` appear in the timeline picker instead of waiting for the
  whole recipe to succeed.
- Newer manual edits are never overwritten by the runner's later state write.
- **Jobs can be cancelled or removed at any time.** Cancelling a running job
  sets the FFmpeg cancellation event, and force stop/remove deletes the job from
  the queue and store. The Activity drawer now has Cancel, Force stop, Dismiss,
  and Clear finished actions.
- Cancelling or removing a queued job drains the next worker immediately.
- Export steps report per-target progress and honour cancellation.

### Notes

- MP4 is still available through the render queue and the Edit tab, with its
  existing revision tracking and cancellation.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.31.0] - 2026-11-02

### Added

- **Live compositor for Recut playback.** Crossfades and fade-to-black now
  compose in the browser with paired video/audio layers, overlays render at
  their timeline position with their opacity and size, and structured title
  cards plus lower thirds appear in output time.
- Track mute/solo is honoured live: the audio gain drops to zero and a muted
  video track renders black.
- `GET /jobs/{id}/overlays/{overlay_id}/file` serves overlay assets with the
  same allowed-root validation as the rest of the API.
- The timeline payload now carries `titles` cues and each clip reports whether
  its transition includes audio.

### Notes

- FFmpeg colour/audio filters and clip transforms still fall back to the
  rendered preview because approximating them in CSS/Web Audio would be
  inaccurate.
- ASS files without `titles.json` also fall back; structured titles are live.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.30.0] - 2026-11-02

### Added

- **Editable Recut cut boundaries.** Inactive segments can be resized with edge
  handles in the Recut canvas or with Start/End controls in the Recut
  inspector. Adjacent active clips grow or shrink to match, the active timeline
  is repacked, and every change participates in undo/redo and the ETag revision
  path.
- The timeline API accepts `action: "recut"` with new source `start_sec` and
  `end_sec` for an inactive segment.

### Notes

- Edges without an adjacent active clip stay fixed, so a leading or trailing
  silent range cannot be extended into unassigned media.
- Inactive reasons are preserved when a cut is adjusted.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.29.0] - 2026-11-02

### Added

- **Recut recipes create inactive segments automatically.** The VAD node emits
  silence spans, the retake node emits retake and manual spans, and the timeline
  node turns the gaps around final padded speech into inactive segments with the
  matching reason. No separate approval flow is required.
- Typed `InactiveSpan` values and `inactive_spans` ports connect the nodes.
- The timeline payload now carries auto-generated `inactive` source ranges for
  the Recut view and the live player.

### Changed

- Portable runs use the same inactive-segment construction as recipes.
- Recut recipes wire silence and retake spans explicitly instead of relying on
  implicit context.

### Notes

- Inactive segments are derived from the complement of the final padded speech,
  so manual deactivation remains available for corrections.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.28.0] - 2026-11-02

### Added

- **Live Recut playback in the editor.** Hard-cut timelines play the source
  directly and jump over inactive ranges. The player shows source and output
  time, preloads through the source stream, and can advance to the next active
  segment.
- `GET /jobs/{id}/source/file` streams the source with Range support.
- The timeline payload reports `live_eligible` and `live_reason`; complex
  timelines fall back to the rendered preview instead of playing inaccurately.

### Notes

- Live eligibility requires hard cuts, paired audio (J/L offsets supported via a
  separate audio element), identity transforms, no transitions/overlays/ASS/
  filters, and no track mute/solo.
- Full-tree coverage is 96.0%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.27.0] - 2026-11-02

### Added

- **Non-destructive inactive segments.** Clips can be deactivated without
  losing their source ranges. `ProjectState.inactive_segments` keeps the paired
  video/audio payloads and the reason (`manual`, `silence`, `retake`).
- **Normal and Recut timeline views.** Normal keeps the compacted active
  timeline. Recut shows the source-time timeline with active clips in blue and
  inactive clips in red; the choice is remembered.
- `deactivate` and `activate` timeline actions participate in undo/redo,
  revision checks, and the ETag edit path.
- The timeline payload now includes `source_duration_sec`, source positions for
  video clips, and the inactive segment list.

### Notes

- The Recut view is visual and editable in this phase. Playback that skips
  inactive regions live is the next phase.
- MP4/NLE exports continue to use only active segments.
- Full-tree coverage is 96.2%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.26.0] - 2026-11-02

### Changed

- **One segmented MP4 renderer with a persistent cache.** The separate
  incremental renderer was removed. Long and crossfade timelines render video
  groups once, cache them atomically under `render/segments`, and reuse
  unchanged groups from both preview and final render.
- Preview and render now share the same audio/video filter and path inputs.
- Segment cache keys include the source file, clip ranges/transforms, encoder
  settings, scale, and cache version.

### Removed

- **Legacy CLI `videoflow run`.** Use `videoflow recipe run`.
- **Projects.** The unused project CRUD records, panel, client types, routes,
  assistant read tool, tests, and documentation were deleted; recipe jobs are
  the only project-producing path.
- The dead crossfade branch in the classic filter-graph builder; any crossfade
  timeline is routed through the segmented renderer.
- The unused timeline `preview_url` field.

### Notes

- Full-tree coverage is 96.2%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.25.3] - 2026-11-02

### Fixed

- **Broken settings no longer fail silently.** An unreadable
  `settings.json` still falls back to defaults, but reports
  `settings_error`, fails the doctor settings check, and raises a global
  warning in the UI.
- **Database failures are visible.** SQLite read/write errors set
  `database_error` in `GET /system`, feed the doctor check, and are logged
  instead of being swallowed.
- **Network and timeout failures reach the global error path.** API requests
  abort after ten minutes and emit the same notification event as HTTP errors.

### Changed

- **MCP job lists omit embedded recipes by default.**
  `videoflow_list_jobs(..., summary=true)` matches the API summary payload.
- Removed the remaining unused client helpers for job-first state, URL import,
  media probe, filesystem roots, model install, config transfer, project
  updates, B-roll reads, and Short LLM analysis. Every exported client function
  is now called by the UI.

### Notes

- Full-tree coverage is 96.2%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.25.2] - 2026-11-02

### Changed

- **Previews render once at proxy height.** The old full-resolution render plus
  a second transcode is gone; previews are encoded directly at the configured
  proxy height and written atomically.
- **Audio-only filters no longer re-encode video.** Long segmented timelines
  apply audio filters on the audio track and copy the video, skipping a whole
  video encode.
- **Timeline edits reload less.** Clip, style, overlay, undo, and redo changes
  no longer refetch assets or review/thumbnail data; the four deliverable calls
  run in parallel on initial load.
- **The job list can omit embedded recipes.** `GET /jobs?summary=true` keeps the
  fields the UI needs and drops the full recipe document from every row; the
  shell uses it for its eight-second poll.
- **SQLite initializes once per database.** Schema checks run on the first
  connection instead of every connection, and asset scans upsert in one
  transaction instead of one connection per file.
- **Maintenance prunes preview frames, render segments, legacy preview
  intermediates, and stale partial files** alongside checkpoints and B-roll.
- Repeated API errors are deduplicated, network failures reach the global
  notification path, and background polling pauses while the window is hidden.

### Notes

- Full-tree coverage is 96.2%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.25.1] - 2026-11-02

### Fixed

- **Rendered files are current or absent.** MP4 and preview outputs are written
  atomically and only become `ready` with a manifest matching the project
  state, filter files, titles, and proxy height. A failed, cancelled, or stale
  render can no longer be served as current after a restart.
- **Previews never hide newer edits.** The preview manifest records the timeline
  revision; the UI keeps the preview marked outdated and queues another pass
  when the timeline changed during rendering. `WaveformStrip` reloads when the
  preview URL changes.
- **Waveforms align after cuts.** The timeline asks for the clip's source range
  (`source_in_sec`/`source_out_sec`) instead of its timeline position.
- **Frame previews use the edited picture.** `/frame` now maps a timeline
  moment to the matching source frame, or reads the current preview, instead of
  rendering the raw source at the same timestamp.
- **Long renders no longer report a false timeout.** The UI follows render and
  preview status for up to two hours, matching the server's FFmpeg budget.
- **Concurrent tabs cannot overwrite each other.** Timeline edits send
  `If-Match`; the UI reloads on `412`. Batch edits now enforce the same check.
- **Batch and MCP step runs validate ports.** Invalid wiring is rejected before
  a batch or step starts.
- **Long crossfade timelines render in bounded groups.** Contiguous crossfades
  are rendered as cached groups with a separate audio graph, followed by the
  finishing pass. The monolithic graph is no longer used for long timelines.
- **Segment and group caches are atomic** and keyed by a cache version, so a
  crashed render cannot poison later renders.

### Changed

- Segment rendering seeks the source before decoding each clip, removing the
  quadratic prefix decode. Repeated renders reuse unchanged segments.
- Project pages are described as source/output bookmarks; the inert “Open run”
  action was removed.

### Notes

- Full-tree coverage is 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.25.0] - 2026-10-27

### Changed

- **Wiring lists every port.** The wire dialog shows all outputs and inputs;
  incompatible ports stay visible but disabled inside an accordion. The node
  inspector has a **Wiring** button that opens the same dialog.
- **The recipe owns its paths.** The optional run source and workspace fields
  are gone from the builder. The ingest node supplies the source, the job
  supplies the output, and NLE validation and run history open a workspace
  dialog seeded from the last job output.
- **Timeline preview sits above the canvas** so the player and waveform lead
  the edit surface instead of trailing the timeline.
- **The welcome guide moved to the header.** An inline onboarding card is
  replaced by a **Guide** button that opens the same four steps in a modal, and
  dismissal is remembered.
- **Modals render in a portal above the area navigation.** JSON editor, wire,
  library, config, history, and tour dialogs share one z-index ladder; the
  area navigation can no longer paint over the JSON editor.

### Fixed

- Stacking order is covered by tests: the JSON editor and wire dialog stay
  above the area navigation.
- Removed the dead job-first client helper and the stale project-to-recipes
  hand-off that wrote an unused `videoflow.project` localStorage key.
- A recipe run without a source now says to set the ingest node source instead
  of suggesting a run-source field that no longer exists.

### Notes

- Full-tree coverage is 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.24.0] - 2026-10-27

### Fixed

- **Long MP4 exports no longer run out of memory.** Timelines above 16 hard-cut
  segments render each video segment separately, concatenate the video, render
  the audio timeline, and apply finishing filters in one bounded final pass.
- **SIGKILL is explained instead of reported as "unknown error".** FFmpeg errors
  now carry the exit code, signal, command, and stderr; a kill without stderr
  says it was likely an out-of-memory termination.
- **Backend error details reach the UI.** API errors preserve status, code,
  command, stderr, and validation errors; a global notification shows every
  failed request with expandable details.
- Job cards, render status, and preview status now show structured error
  details, not just a one-line message.

### Added

- Real FFmpeg media tests for long MP4 timelines, J/L-cut-safe audio, global
  colour/audio filters, ASS titles, overlays, duration, and stream validation.

### Notes

- Full-tree coverage is 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.

## [2.23.0] - 2026-10-26

### Added

- **Guided builder tour.** A three-step tour explains graph building, inspection,
  and multi-selection.
- **Mobile inspector drawer.** On narrow screens the inspector opens as a bottom
  sheet with a dismiss backdrop.
- **Icon consistency.** Library, assets, timeline markers, B-roll controls, and
  favorites use the shared SVG icon set.
- **Fit selected nodes.** Frame the current multi-selection in the viewport.

### Changed

- **Domain I/O isolation is complete.** Steps no longer leak `artifacts`,
  `metadata`, `shorts`, `selected_shorts`, `short_captions`, transcript changes,
  or speech spans through ambient context copies. Every domain value crosses a
  declared output port; only hashes, cache bookkeeping, and warnings remain as
  runner diagnostics.

### Notes

- Full-tree coverage is 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.
- Planned and partial steps remain documented limitations.

## [2.22.0] - 2026-10-26

### Added

- **Help metadata for every parameter.** Labels, descriptions, units, groups,
  and placeholders now ship in each step manifest, so every field has a tooltip
  in the node and inspector.
- **Local SVG icon system.** Areas, tabs, steps, toolbar actions, and inspector
  sections use representative icons instead of Unicode glyphs.
- **Hierarchical builder toolbar.** Primary Add/Run, secondary Save/Validate/
  Inspector, icon undo/redo, and a More menu for batch, NLE validation, config,
  layout, history, and export actions.
- **Builder command palette and shortcuts.** Recipe actions are searchable in
  the palette; Ctrl/Cmd+S, Ctrl/Cmd+Enter, Ctrl/Cmd+C/V, and Delete work in the
  graph.
- **Resizable inspector.** Drag the left edge to resize; width is remembered,
  sections collapse, and fields can be filtered.
- **Path picker recents and favorites.** Recent folders and starred folders are
  stored locally per machine.
- **Preset management.** Rename, duplicate, and see how many values differ from
  the current node.
- **Graph productivity.** Node search dims non-matches; multi-select can align,
  duplicate, or delete; copied nodes can be pasted; wiring can be disconnected.
- **Recipe version comparison.** Compare a saved version with the current graph
  without restoring it first.
- **Design primitives.** Shared Button, IconButton, and Section components.
- **Contextual onboarding.** A fourth onboarding step explains the inspector,
  autosave, and undo.

### Notes

- Full-tree coverage remains above the 95% gate at 96.4%.
- 3.0 is still blocked only by the two manual QA sign-offs.
- No new planned step became available; `content.*`, `publish.webhook`, and the
  partial steps remain documented limitations.

## [2.21.0] - 2026-10-26

### Added

- **Full-tree coverage gate met.** 96.4% (19,347/20,069 statements) with 1,405
  unit/contract tests, including new coverage for adapters, CLI, MCP tools, API
  routes, step runners, services, and exporters.
- **Docked recipe inspector.** The inspector now sits beside the canvas on wide
  screens instead of covering the graph.

### Fixed

- Missing music/image/font assets return `404 asset_not_found` instead of a 500.
- Invalid config imports return `422 invalid_config`.
- A shadowed duplicate artifacts route was removed.
- Missing local models raise a domain error instead of `KeyError`.
- Duplicate entries in LLM Short rankings are ignored.
- Disabling Short captions no longer leaves a stale subtitle reference.
- Publishing and B-roll history tolerate non-object JSON stores.

### Notes

- Pure step I/O and the two manual QA sign-offs remain open for 3.0.
- Voice cloning stays shell-only by decision; synthesis reports
  `capability_unavailable`.

## [2.20.0] - 2026-10-26

### Added

- **Node presets library.** Built-in and operator-created presets per step type,
  with create, edit, delete, favorite, and update-from-current-values.
- **Node option catalogs.** `GET /api/v1/node-options` and provider pickers for
  ASR/TTS steps, populated from the configured providers.
- **Optional run roots.** Source and workspace are derived from the ingest node
  and source folder when the run form is left empty.
- **Port wiring shows every port.** Incompatible inputs remain visible but
  disabled, with type labels and reasons.
- **Navigation icons and field help.** Icons for areas/tabs and tooltips for
  node descriptions and every documented field.
- **Per-step context isolation.** Steps run against a scoped context copy; only
  declared ports and ambient compatibility state are merged back.

### Notes

- Full-tree coverage is 81.9%; the 95% gate remains open.
- Pure step I/O and Kdenlive/a11y manual QA remain open.

## [2.19.0] - 2026-10-26

### Added

- **Global recut presets:** Recut Podcast (J-cuts + retakes), Recut Lecture
  (hard cuts, wide handles), and Recut Social (L-cuts + retakes).
- Recipe presets are regular recipes, so they appear in Favorites/Recent/All,
  support branch wiring, and export MP4 + Resolve/Premiere/Kdenlive.

### Fixed

- Node output-folder copies deduplicate artifacts and preserve pipeline refs.
- Node media/output paths are validated against allowed roots during recipe
  validation, not only at execution.
## [2.18.0] - 2026-10-26

### Added

- **Node-native media input.** `ingest` owns a media picker; any node with a
  `media` input can choose a file when the port is unwired.
- **Node output destinations.** File-producing nodes can pass artifacts to the
  next node or save a copy to a chosen folder, validated against allowed roots.
- **Inputs / Config / Outputs node layout.** Ports, presets/schema fields, and
  destination policy are visually separated and color-coded.
- **Voice clone shell.** Provider contract, consent metadata, status/profiles
  API, and an AI providers UI card; synthesis returns `not_implemented`.
- **Recipe tags UI.** Tags are editable in the recipe library.
- **Kdenlive-only NLE plan.** Resolve and Premiere removed from installation/QA;
  Kdenlive Flatpak 26.08.2 is the manual target.

### Changed

- `RecipeStep` gained `media_override`, `output_mode`, and `output_dir`.
- Recipe validation and the runner enforce node-level media/output paths.
- Output folders copy the node's artifacts while preserving pipeline refs.

## [2.17.1] - 2026-10-25

### Added

- **Inspector port rewiring.** Every selected node lists its inputs with a
  compatible-output dropdown, including a "Not wired" option. Rewiring updates
  the dependency edge, label, undo stack, and serialized recipe.

### Fixed

- Port validation now requires the source node to be in the target's dependency
  ancestry, not merely earlier in the topological order.

## [2.17.0] - 2026-10-25

### Added

- **Typed data ports.** Every registered step declares typed inputs and outputs;
  recipes can bind `node.port` to `node.port` via `inputs`.
- **Port wiring in the UI.** Nodes show their ports, edge labels show the
  mapping, and the Wire ports dialog filters compatible types.
- **Branching recipes.** Two VADs or two timelines can run independently; cache
  fingerprints include wired input hashes.
- **Legacy compatibility.** Recipes without explicit `inputs` keep the existing
  implicit context behaviour.
- **Schema-driven controls.** Sliders with numeric companions, segmented
  controls/dropdowns, switches, chips, path/colour pickers, defaults, resets,
  field groups, and node presets.
- **Validation fix.** Recipe validation resolves variables before validating
  step parameters.

## [2.16.0] - 2026-10-25

### Changed

- **Recut configuration moved into the nodes.** `recut_replacement` and
  `recut_replacement_retakes` no longer expose node-local settings as recipe
  inputs; VAD, retake, timeline, and export defaults live in each step.
- **Recut wiring.** The built-in Recut recipes now use explicit ports for
  ingest→VAD→timeline→export and the retakes branch.
- **UI version and tooltips.** The UI version comes from the package at build
  time, and help tooltips are fixed-position portals with viewport collision.

## [2.15.1] - 2026-10-25

### Fixed

- **Recut padding is applied once.** The VAD step no longer pads spans before the
  timeline when the recipe exposes `pad_before_ms`/`pad_after_ms`; the timeline
  remains the single owner of handles, so cuts are not lengthened twice.

## [2.15.0] - 2026-10-25

### Added

- **Recut Replacement** built-in recipe with detailed VAD controls:
  noise/speech thresholds, minimum silence, minimum speech, left/right pads,
  short-spike suppression, and tiny-gap merging.
- **Recut Replacement + retakes** variant that adds transcription and retake
  culling before the cut.
- **Cut mode** `hard | j_cut | l_cut | custom` on the timeline step, with
  configurable offset, crossfade, fades, and handle checks.
- **Four outputs from one recut:** MP4, FCPXML (Resolve), XMEML (Premiere),
  and Kdenlive.
- **Recipe organization on the server:** favorites, recent runs, use counts,
  and tags in `<home>/recipe_meta.json`, exposed through the API and MCP.
- **Recipe library UI:** Favorites, Recent, All, search, and star toggles.
- **Tooltip portal:** help tooltips are fixed-position and no longer clipped by
  the recipe canvas container.
- **UI version injection:** the UI reads the package version at build time, so
  the version badge no longer drifts from the server.

### Changed

- `audio.vad` accepts `spike_suppression_ms` and `merge_gap_ms`.
- Recut recipes default to hard cuts and export all four targets.
## [2.14.1] - 2026-10-25

### Added

- **Incremental crossfade.** Adjacent clips joined by a crossfade render as a
  cached xfade group; unchanged groups are reused and the full graph remains the
  fallback for ineligible timelines.
- **Multi-process queue worker.** `queue_worker.run_once/serve` claims with a
  lease, keeps a heartbeat, and can start a manager with `load_store=False` so
  another process does not steal queued jobs.
- **Frame prefetch.** `GET /jobs/{id}/frames` serves a bounded batch with cache
  hit reporting; the timeline preloads the next frames while scrubbing.
- **Quality gates.** axe WCAG A/AA test, shell visual baseline, 1,000-clip UI
  performance guard, p95/p99/memory load metrics, and `scripts/gate_local.sh`.

### Changed

- Missing export/prune directories now return `404` instead of a generic `500`.
- Layer coverage: API 85.2%, jobs 90.8%, exporters 95.0%, MCP 80.3%; full tree
  81.7% (3.0 still blocked at 95%).

## [2.14.0] - 2026-10-25

### Added

- **Incremental render expansion.** Segment cache now keeps per-clip
  `fade_to_black` and overlays incremental; crossfades still use the full graph
  with a safe fallback.
- **Frame proxy cache.** `GET /jobs/{id}/frame?height=` caches per revision and
  height, so scrubbing invalidates automatically after an edit.
- **Multi-process queue claim.** Atomic SQLite claim with worker leases,
  heartbeat ownership checks, and expired-lease recovery (`queue_claim.py`).
- **Observability.** Every log line carries `job_id` for correlation.
- **Property tests.** Recipe parsing and timeline edits are fuzzed for invalid
  ranges and clean rejection.
- **Circuit breaker and cost budget** for LLM providers, with actionable errors.

## [2.13.0] - 2026-10-25

### Added

- **Projects.** `GET/POST/PATCH/DELETE /api/v1/projects` with local JSON records,
  Produce → Projects, and a "Use in Recipes" handoff.
- **Assistant tool-calling.** Allowlisted read/write tools, two-step approval,
  clip-level diff, per-turn tokens/cost, conversation history, and a single-use
  approval id.
- **Run graph.** Step nodes, edges, per-step duration, p50/p95 by recipe, retry
  policy, and previous-run comparison.
- **Variant comparison.** Recipe variants, Shorts, and thumbnail metrics in one
  list with a persisted winner.

## [2.12.0] - 2026-10-25

### Added

- **Complete EN/PT catalog.** Every visible static string in the Svelte panels has
  a PT-BR entry, enforced by a coverage test.
- **Onboarding.** Three-step first-run card with persisted dismissal.
- **MCP contract.** Behavior annotations on every tool, three prompts
  (`produce`, `review`, `deliver`), and paginated list tools.
- **OpenAPI contract.** Error envelope, examples for timeline/run/logs/projects,
  ETag/If-Match on timeline writes, and explicit API version.
- **Accessibility and responsiveness.** Arrow/Home/End tab navigation, narrow
  viewport and PT-BR locale E2E coverage, `docs/errors.md`.

## [2.11.0] - 2026-10-25

### Added

- **Five-area navigation.** Produce, Edit, Runs, Library, and Setup replace the
  flat 13-tab bar, with sub-tabs, breadcrumbs, persisted last tab, and legacy
  hash redirects (`#assets`, `#automation`, `#copilot`, `#library`, `#plugins`,
  `#integrations`).
- **Naming pass.** Runs, Schedules, Media, Brand library, Assistant, AI models,
  AI providers, Local services, Extensions, Connect.
- **Help system.** `HelpTip`, `FieldHint`, `EmptyState`, `StatusBadge`, units in
  labels, help tips on every Setup panel and the main editors.
- **Searchable settings** with section filtering, units, help tips, and
  discard-changes.
- **Keyboard navigation** for area and sub-tab tablists (arrows, Home, End).
- **Copy standards.** `docs/ui-copy.md` and `docs/settings.md`.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Remaining for 3.0: long help-text i18n, voice cloning, full-tree coverage,
  and manual NLE/assistive-technology QA.

## [2.10.0] - 2026-10-25

### Added

- **MCP surface finished.** 78 tools and 5 resources covering jobs, pause/
  priority, timeline read, overlays, clip comments, Copilot, cost, export
  validation, plugins, backup, and frame extraction. New resource
  `videoflow://docs/integrations`.
- **Integration area.** New Integrations tab and `docs/integrations.md` with
  copy-ready OpenCode stdio/HTTP setup, `opencode.jsonc` examples, DeepSeek
  model/provider setup, Paperclip DeepSeek agent + MCP/REST workflow, prompts,
  security notes, and troubleshooting.
- **API docs.** Copilot endpoints, frame/overlays/comments, pause/priority,
  cost metrics, and MCP tool counts documented.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Remaining: long help-text i18n, voice cloning, full-tree coverage, and manual
  NLE/assistive-technology QA.

## [2.9.0] - 2026-10-24

### Added

- **Segment-cached timeline render.** Simple cut timelines render each clip to a
  cached segment, reuse unchanged segments, and concatenate without re-encoding
  everything. Timelines with transitions, overlays, titles, filters, or
  non-aligned audio fall back to the full exporter.
- **Frame progress.** `FFmpegAdapter.render` parses `-progress` and the render
  queue maps frame counts to the job percentage.
- **Frame preview.** Scrubbing debounces a cached JPEG and an async video seek;
  the playhead shows the exact frame.
- **Resource-aware parallelism.** `flow.map` caps workers by CPU, available
  memory, and `VIDEOWFLOW_PROVIDER_CONCURRENCY`.
- **Copilot.** `POST /api/v1/copilot/recipe` drafts and validates recipes;
  `POST /api/v1/jobs/{id}/copilot/timeline` proposes or applies validated
  timeline edits. Provider/service setup is documented in `docs/copilot.md`.
- Copilot tab with recipe draft/save and timeline apply.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Remaining: long help-text i18n, voice cloning, full-tree coverage, and manual
  NLE/assistive-technology QA.

## [2.8.0] - 2026-10-24

### Added

- **Typed job rows and retries.** The `jobs` table gains status, priority,
  attempts, next_run, lease, progress, source/output/recipe/variables, and
  timestamps. Jobs can opt into retry with `max_attempts` and
  `retry_backoff_seconds`; a retry loop re-drains when due. Scheduled runs use
  an automatic idempotency key from schedule, source, size, and mtime.
- **Frame preview.** `GET /jobs/{id}/frame?time=` extracts a cached JPEG at the
  playhead; the timeline debounces a frame image while scrubbing.
- **Resource-aware map.** `flow.map` caps workers by available CPUs and warns
  when the requested parallelism is clamped.
- **Per-service log rotation.** Service logs rotate to two generations before a
  new process appends.
- **Optimistic rollback.** Pause/resume and priority update the card, then
  revert on error.
- **More PT-BR glossary.** Additional panel labels and headings.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Remaining: long help-text i18n, voice cloning, per-clip incremental render,
  full-tree coverage, and manual NLE/assistive-technology QA.

## [2.7.0] - 2026-10-24

### Added

- **True Kdenlive cross-dissolve.** Video is written to two alternating tracks;
  a crossfade extends the outgoing clip's source tail by the transition length
  and animates affine opacity on the incoming (or outgoing) top track, with two
  `qtblend` composites in the sequence tractor. Fade-to-black keeps the
  single-clip opacity ramps.
- The Kdenlive validator and tests now read both video playlists and assert the
  two-track structure and opacity keyframes.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- Long help-text i18n, voice cloning, full-tree coverage, and the manual
  NLE/assistive-technology gates remain open.

## [2.6.0] - 2026-10-24

### Added

- **NLE overlays and drag e2e.** Timeline overlays join the B-roll lane in all
  three documents (XMEML still frames, Kdenlive `qimage`), with a Playwright
  drag test.
- **Semantic B-roll option.** Local sentence-transformers model via
  `VIDEOWFLOW_EMBEDDING_MODEL`; TF-IDF remains the fallback.
- **Dubbing hardening.** Duration alignment retry, translation review files, and
  ordered TTS provider fallback.
- **Hook and duration A/B.** `shorts.ab` plus the `hook_duration_ab` recipe.
- **Video-track mute.** Render and preview draw black frames when V1 is muted.
- **Parallel map everywhere.** `flow.map` runs any collection in parallel, with
  isolated child contexts.
- **Assets pagination.** SQL `LIMIT/OFFSET` and filtered asset queries.
- **Plugin write policy.** `filesystem` permission and rejection of absolute
  paths outside the plugin folder.
- **Job DAG and confirmations.** Stage pills in the dashboard; confirmation for
  plugin enable and managed service start/stop.
- **Embedded plugin panels.** Panels open inside the shell in a sandboxed iframe.
- **Cost estimate and expanded golden set.** Token prices for known models,
  approval-rate metric, and seven golden cases including multi-speaker, gaps,
  and scene changes.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums.
- True Kdenlive cross-dissolve, full long-text i18n, voice cloning, full-tree
  coverage, and the manual NLE/assistive-technology gates remain open.

## [2.5.0] - 2026-10-24

### Added

- **Plugin SDK for exporters and providers.** `videoflow/plugin_api.py` exposes
  `register_exporter`, `register_provider`, and `register_panel`.
  `export_timeline` dispatches unknown targets to a plugin exporter and
  `first_provider` falls back to a plugin provider.
- **Static plugin sandbox.** `application/plugin_sandbox.py` parses the entry
  module before import and blocks shell/network imports and exec-style calls
  unless the manifest grants `shell` or `network`. Blocked plugins report the
  violations instead of loading.
- **Fault-injection suite.** Corrupt database, corrupt migration input,
  non-writable output, and corrupt project state all fail with typed errors and
  never produce a success record.
- **Log rotation and scheduled backups.** `rotate_log` retains two generations;
  `scheduled_backup` writes timestamped ZIPs and prunes to `keep`. Opt in with
  `VIDEOWFLOW_BACKUP_ON_START=1` or `POST /api/v1/maintenance/backup`.
- **Accessibility pass.** `:focus-visible`, focus traps in every dialog, focus
  restoration in the palette, `prefers-reduced-motion`, and keyboard-only
  Playwright flows.
- **Large-timeline stress test.** 1,000 clips exported through all three NLE
  writers under a ten-second budget.
- **Schema 1.x migration test.** A version-1 database migrates to version 2 with
  rows and defaults preserved.
- `docs/plugins.md` and `docs/hardening.md`.

- **Execution control.** Jobs can be paused and resumed; priority is editable
  and reorders the queue.
- **Timeline editing.** Slide, duplicate, per-clip comments, and a right-click
  context menu for split, duplicate, delete, ripple delete, slide, markers, and
  comments.
- **Incremental Shorts.** `shorts.render` writes `render-manifest.json` and
  reuses an unchanged Short; the MP4 render queue reuses an unchanged timeline.
- **Native chapters.** `chapters.json` becomes NLE markers in all three
  documents.
- **Theme and density.** Light, dark, and high-contrast themes through tokens;
  compact density; AA focus, focus traps, reduced motion.
- **Crash reports and token metrics.** Unhandled API errors write a minimal
  JSON report; LLM usage is accumulated at `GET /api/v1/metrics/cost`.
- **Plugin panels.** The Plugins tab lists sandbox status and links registered
  panels.
- **Assets on the timeline.** Drag an image or video from the timeline asset
  rail; the overlay is stored in `ProjectState.overlays` with `asset_id`,
  frame timing, position, size, and opacity, and is composited by the MP4
  exporter.

- **Optional semantic B-roll.** A local sentence-transformers directory enables
  embedding matching; TF-IDF remains the automatic fallback.
- **Dubbing hardening.** Duration drift triggers one speed-corrected retry,
  each dub writes a translation-review file, and the step tries every configured
  TTS provider before warning.
- **Hook and duration A/B.** `shorts.ab` clones selected Shorts into hook and
  duration variants, and the `hook_duration_ab` recipe renders them.
- **Overlays in the NLEs.** Timeline overlays join the B-roll lane; XMEML marks
  still frames and Kdenlive uses `qimage` producers.
- **Panel glossary.** A runtime PT-BR glossary translates the dense panels'
  headings, actions, and common labels without rewriting every template.

### Changed

- `RecipeSchedule`, `PluginManifest`, settings, providers, and schedules gain
  versioned migration helpers with default filling.
- Version bumped to 2.5.0 for the server and UI bundle.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums. No GitHub Actions,
  no publishing, no multiuser.
- The plugin sandbox is a static allowlist, not an OS sandbox: a plugin with the
  `shell` permission runs as the service user.
- Manual NLE import checks and manual screen-reader/200% zoom checks remain on
  the checklist; the host lacks the NLEs.
- Kept releases: v2.5.0, v2.4.0, v2.0.0. v1.0.0 is pruned by the three-release
  retention rule.

## [2.4.0] - 2026-10-24

### Added

- **Native NLE finishing.** FCPXML, XMEML, and Kdenlive exports now carry
  titles, sequence markers, colour filters, B-roll, and the audio master,
  driven by `exporters/extras.py` and `application/nle_extras.py`.
- **FCPXML** writes native `title` elements, `marker` elements,
  `filter-video` colour filters, B-roll on lane 2, and the master stem on
  lane 4.
- **XMEML** writes `generatoritem` titles, sequence markers, colour filters, a
  second video track for B-roll, and a second audio track for the master.
- **Kdenlive** writes `kdenlivetitle` producers, guides in the document
  properties, an overlay playlist with `qtblend`, a stem playlist with `mix`,
  and `lift_gamma_gain` colour filters.
- **`scripts/qa_nle.py`** compares an export directory with the job output and
  fails on missing native elements; the validator also reports titles, markers,
  colour filters, B-roll, stems, and join warnings.
- Tests cover all three documents and the QA comparison.

### Changed

- `export_timeline` accepts `extras`; `export.nle` builds them from the job
  output (markers, ASS titles, B-roll plan, colour and audio filter files,
  `master.wav`).
- The sidecar manifest now says the native timeline is the primary finishing
  path and the sidecars are the interchange copy.
- Version bumped to 2.4.0 for the server and UI bundle.

### Notes

- Local release: Linux binary + AppImage + SBOM + checksums. No GitHub Actions,
  no publishing, no multiuser.
- Manual import validation in Resolve, Premiere, and Kdenlive remains pending:
  the three NLEs are not installed on this host. The checklist and the
  automated structural checks are in `docs/nle-qa.md`.
- Kept releases: v2.4.0, v2.0.0, v1.0.0. v0.95.0 was pruned by the three-release
  retention rule.

## [2.3.0] - 2026-10-24

### Added

- **Golden set and calibration.** `tests/golden/shorts.json`, a pure
  `application/scoring.py` module, six channel profiles (`default`, `hook`,
  `education`, `podcast`, `tiktok`, `youtube`), and
  `scripts/shorts_golden.py`. The calibrated profiles reach precision@1 1.00
  against a 0.75 baseline, with zero duplicates and 100% coverage.
- **Profile before selection.** `shorts.select` accepts `profile` (also
  `shorts_profile` in job options), so weights influence which windows are
  selected, not only how they are re-ranked afterwards.
- **Shot-aware B-roll.** `assets.match` scores assets per detected shot, sets
  the cutaway `start_sec` inside the Short, records `shot_id`, and writes
  `broll-licenses.json` with attribution and license for every used asset.
- **SFX library.** `GET/POST/DELETE /api/v1/assets/sfx`, storage under
  `assets/sfx`, and an upload/delete section in the Library tab.
- **Delivery package.** `delivery.package` copies the winning thumbnail to
  `delivery/thumbnail.png` and writes a manifest with Shorts, metadata, music,
  SFX, B-roll, and licenses.
- **Localized recipe.** `localized_shorts` runs `localization.dub` after the
  Short render, with a mirrored `recipes/localized_shorts.json`.
- Media test renders a Short with music and SFX in the same pass.

### Changed

- `shorts.score` now shares `rerank`, `profile_weights`, and duplicate
  similarity with the golden evaluator instead of keeping a second copy.
- Portuguese hook detection accepts unaccented `voce`, fixing a real miss in
  the quality bonus.
- Recipe, preset, and project-state schemas are regenerated for the additive
  `profile` field.
- Version bumped to 2.3.0 for the server and UI bundle.

### Notes

- Local-only development build. No release artifact was produced for 2.3.0.
- Embedding-based B-roll and local clone dubbing remain provider work; TF-IDF,
  shot matching, and the configured TTS path are what 2.3.0 ships.

## [2.2.0] - 2026-10-24

### Added

- **Real clip waveforms.** `GET /api/v1/jobs/{id}/timeline/waveform` decodes
  the source once, computes normalised RMS peaks at 50 ms resolution, caches
  them under `<home>/waveforms`, and slices any timeline range. The canvas draws
  the real peaks and falls back to synthetic bars when the source is missing.
- **Slip edit.** `action: "slip"` shifts the source in/out of a clip without
  moving it on the timeline, for video and audio, bounded by the media length.
- **Group trim and ripple trim in the canvas.** Dragging an edge with several
  clips selected trims them together; `Shift` + edge drag ripples the trim.
  `Alt` + drag slips the clip.
- **Timeline virtualization.** Only clips, captions, and audio bars inside the
  visible window (plus a three-second margin) are drawn, and the canvas redraws
  on scroll. A synthetic 1,000-clip timeline stays responsive.
- **Preview scheduler.** The preview is marked `outdated` after every edit and
  rebuilt automatically after a 1.2 s debounce when `Auto preview` is on.
- **Track enforcement.** Locked video/audio tracks reject clip edits with
  `409 state_not_ready`; muted audio tracks render and preview with
  `volume=0`, and `solo` overrides mute.

### Changed

- Timeline DTO exposes `audio[].source_in_sec`, `audio[].source_out_sec`, and
  `media {source_path, audio_sample_rate}` for waveform requests.
- Caption drawing no longer caps at 500 entries; visibility decides what is
  drawn.
- Version bumped to 2.2.0 for the server and UI bundle.

### Notes

- Local-only development build. No release artifact was produced for 2.2.0.
- Dragging library assets onto the timeline needs a clip/overlay state model
  and is scheduled with the NLE work, not this phase.

## [2.1.0] - 2026-10-24

### Added

- **Professional shell.** Command palette (`Ctrl/Cmd+K`), keyboard shortcut
  reference (`?`), activity drawer (`U`), notification center (`N`), and
  `g`-prefixed tab jumps.
- **Job dashboard.** New Jobs tab with status buckets, text search, progress,
  next-action guidance, inline errors, guarded cancel, and retry.
- **Retry endpoint.** `POST /api/v1/jobs/{job_id}/retry` re-enqueues failed or
  cancelled jobs with the original source, output, and options.
- **Operational feedback.** Persistent errors and warnings, action buttons on
  notices, and shell-level error/success reporting.
- 12 Vitest tests and 8 Playwright tests for the new shell.

### Changed

- **Real cancellation.** `FFmpegAdapter` runs FFmpeg with `Popen`, polls for
  cancellation, and terminates the whole process group on cancel or timeout.
  Render and preview queues now pass a cancel event, remove partial output, and
  report `cancelled` without leaking processes or files.
- **SQLite is the operational store.** Jobs, assets, and batches load from
  SQLite first and JSON second; interrupted jobs are requeued on startup; reads
  no longer create the home folder as a side effect.
- Version bumped to 2.1.0 for the server and UI bundle.

### Notes

- Local-only development build. No release artifact was produced for 2.1.0.
- `ProjectState` remains the timeline source of truth; SQLite holds operational
  state for jobs, assets, and batches, with JSON kept for interchange.

## [2.0.0] - 2026-10-24

### Added

- **Local automation closure.** Human gate UI, variant comparison, analytics
  weights in scoring, scheduler job reconciliation, persistent priority queue,
  restart requeue, and real thumbnail variants.
- **Media quality.** Real audio onset/beat detection, music and SFX mixing in
  Shorts, per-Short selection reports, and thumbnail winner selection.
- **Dubbing in recipes.** `localization.dub` runs translation + TTS dubbing
  after Short rendering when a TTS provider is configured.
- **Semantic B-roll matching.** TF-IDF cosine matching over asset names/tags and
  the clip transcript, replacing keyword overlap.
- **Library CRUD.** Delete music, image, and font assets from the UI.
- **SQLite migration.** Existing JSON jobs/assets/batches import into SQLite;
  schema version 2; WAL; backup and restore.
- **Plugin step loading.** Local `plugins/<id>` packages with manifests.
- **Accessibility.** Skip-to-content link and improved labels.
- 34 built-in recipes.
- 485 Python tests, 8 media tests, 13 Vitest tests, 19 Playwright tests.

### Notes

- Local-only release: Linux binary + AppImage + SBOM. No GitHub Actions, no
  distribution, no publishing, no multiuser.
- Native NLE titles/color/B-roll remain sidecar-based; manual NLE QA still
  pending.
- Plugin SDK covers steps; providers/exporters/UI panels are not part of this
  local release.
- Full UI i18n and per-clip waveforms remain future work.

## [1.0.0] - 2026-10-24

### Added

- **0.97 — render and media closure.** Real onset/beat detection, music/SFX
  mixing in Shorts, bounded parallel map, thumbnail winner selection, and
  per-Short selection reports.
- **0.98 — Shorts intelligence.** Analytics weights applied to scoring,
  explicit score breakdowns/reports, diversity filtering, and A/B winner
  selection.
- **0.99 — finishing.** NLE structural QA, chapter planning, sidecars for
  titles/color/audio/B-roll, and a finishing recipe.
- **1.0 — local stable.** Persistent priority queue with restart requeue,
  scheduler job reconciliation, human-gate UI, variant comparison, backup
  restore, operational metrics, plugin steps, accessibility skip link, and
  SQLite WAL indices.
- 34 built-in recipes.
- 8 media tests including real beat detection.

### Validation

- 484 Python tests passed.
- 8 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Local release only: Linux binary + AppImage + SBOM. No GitHub Actions.
- Distribution, signing, macOS, Windows local builds, and collaboration remain
  out of scope.
- Native NLE titles/color/B-roll remain sidecar-based; manual NLE QA is still
  required.
- Plugin SDK v1 covers steps, not providers/exporters/UI panels.
- SQLite is an operational index; JSON remains canonical for jobs/assets.
- `flow.map` parallel is bounded for file collections.
- Full UI i18n and per-clip waveforms remain future work.

## [0.96.0] - 2026-10-24

### Added

- **Human gate UI.** Jobs waiting for approval show the gate title, comment
  field, approve/reject buttons, and resume the recipe from checkpoints.
- **Variant comparison.** Job results list every variant with output path,
  segment/short counts, and step count.
- **Analytics feedback.** `shorts.score` now reads analytics weights from
  `analytics.review` or `delivery/analytics-review.json`.
- **Scheduler job tracking.** Schedules reconcile queued/running job ids into
  succeeded/failed/waiting states and surface failures.
- **Persistent job queue.** API/MCP submissions queue instead of failing when
  the worker limit is full; queued jobs survive restart and are requeued.
- **Priority queue.** Jobs accept a priority and drain highest-first.
- **Real thumbnail variants.** `thumbnail.pack` renders different frames/styles
  and copies variants into the shared thumbnails directory.

### Validation

- 481 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- No release was built for this version.
- Native NLE effects, SFX/music mixing in the renderer, and parallel map
  execution remain future work.

## [0.95.0] - 2026-10-24

### Added

- **Recipe variables and expressions.** Typed variables, defaults, enum
  validation, `{{ expression }}` and `$name` substitution, and safe functions
  (`min`, `max`, `clamp`, `if`, `coalesce`).
- **Profiles and dry-run.** Recipe profiles override variables/step params;
  `recipe dry-run` and `POST /recipes/dry-run` return the resolved plan.
- **Variants.** A recipe can run the same DAG into named output folders with
  per-variant variables.
- **Map/reduce/subflows.** `flow.map` and `flow.reduce` operate over files,
  Shorts, sentences, scenes, and assets, with error policy and collected
  results.
- **Human gates.** `human.gate` pauses the job as `waiting_approval`; the resume
  endpoint records the decision and restarts from checkpoints.
- **Short quality scoring.** Multifactor bonuses (completeness, payoff, hook,
  CTA, speaker balance, duration fit), diversity filtering, profiles, and
  optional LLM re-rank.
- **Asset intelligence.** Shot detection, semantic B-roll matching, beat grid,
  and SFX planning.
- **Delivery.** Metadata pack, thumbnail pack, publish queue, analytics review,
  experiment evaluation, chapters, and NLE QA.
- **34 built-in recipes**, including rough cut, captions, NLE export, clean
  audio, chapters, Shorts select/render, best moments, trailer, review gate,
  variants, podcast/interview/webinar/lecture/product/testimonial/livestream,
  B-roll/music/SFX, metadata, thumbnails, publishing, analytics, localization,
  and finishing.
- **SQLite index** for jobs, assets, and batches with WAL and a backup bundle.
- **Plugin SDK v1.** Load `plugins/<id>/plugin.json` and register custom steps.
- **Diagnostics 2.0.** FFmpeg capabilities, CUDA/ONNX, SQLite integrity,
  providers, services, models, metrics, backup, and support bundle.
- **Settings wiring.** Model defaults/device/compute, speech, quality,
  translation, proxy height, runtime host/port/log/open-browser, retry/backoff,
  and locale/theme/density are consumed by the runtime.
- **Library and i18n.** Brand/project templates, presets, fonts, images, music,
  and EN/PT-BR navigation strings.

### Validation

- 477 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Local release only (Linux + AppImage + SBOM). No GitHub Actions.
- Native NLE titles/color/B-roll remain sidecar-based; manual NLE QA is still
  required.
- Windows, distribution, signing, macOS, and collaboration remain out of scope.

## [0.86.0] - 2026-10-23

### Added

- **Settings Hub.** `settings.json` with runtime, paths, models, automation,
  quality, UI, LLM, speech, TTS, stock, and translation sections; export,
  import, reset, environment overrides, and restart-required markers.
- **Runtime wiring.** Settings influence job workers/history, allowed roots,
  cache/models dirs, FFmpeg/FFprobe resolution, scheduler interval, LLM
  temperature/timeout/retries, and TTS/stock defaults.
- **Model Manager 2.0.** Expanded ASR catalog (Faster-Whisper tiny/base/small/
  medium/large-v3 and whisper.cpp base/small/medium), per-capability defaults,
  device/compute/threads, local model registration, and file/checksum
  verification.
- **Service Manager 2.0.** SQLite-backed service definitions with start/stop,
  health checks, autostart, logs, and arbitrary local commands (Ollama, LM
  Studio, whisper.cpp server, Piper, ComfyUI, and others).
- **Library.** Brand templates, project templates, presets, fonts, images, and
  music are available again in the UI.
- **Diagnostics 2.0.** Doctor checks FFmpeg capabilities, CUDA/ONNX providers,
  SQLite integrity, providers, service definitions, models, disk, and settings;
  support bundle ZIP redacts environment values.
- **LLM controls.** Temperature, timeout, max tokens, retries, and JSON mode.

### Validation

- 467 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Local release build only; GitHub Actions is disabled for automatic releases.
- Distribution, signing, macOS packaging, and Windows cross-builds remain out of
  scope.
- Manual NLE QA and per-clip waveforms remain future work.

## [0.80.0] - 2026-10-23

### Added

- **Timeline pro.** Shift-click multi-select, atomic batch edits, group move,
  bulk delete/ripple, ripple trim, real clip thumbnails, markers, and
  per-track mute/solo/lock.
- **Background MP4 render queue.** Progress, cancel, and download; filters,
  titles, color, and audio-master chain are applied.
- **Caption undo.** Caption edits now share the timeline history.
- **Schedule reliability.** SQLite-backed schedules with a JSON migration,
  retry/backoff, run history, watch-file size/mtime signatures, and concurrency
  through the job manager.
- **Provider failover.** LLM chains retry providers in order; ASR/TTS/vision
  read the configured provider when no explicit endpoint is supplied.
- **Secret store.** Environment, OS keyring, or 0600 fallback with presence-only
  API and provider-panel controls.
- **Translation.** `transcript.translate` writes translated JSON and SRT through
  the recipe LLM provider.
- **Delivery metrics.** Review comments and thumbnail CTR metrics; A/B selection.
- **NLE sidecars.** Exports now package titles, LUT/eq, audio-master filters,
  B-roll plans, and markers with instructions.
- **Audio QA.** `audio.qa` measures EBU R128 integrated loudness and true peak
  and warns when out of spec.
- **MCP parity.** Timeline edit, B-roll approval, providers, schedules, and
  review decisions are available as MCP tools.

### Validation

- 464 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Distribution, signing, macOS packaging, and onedir builds remain out of
  scope.
- Manual NLE QA, frame-accurate per-clip waveforms, and translation quality
  review remain future work.

## [0.70.0] - 2026-10-23

### Added

- **Incremental timeline rendering.** The scene layer is rebuilt only when the
  timeline, zoom, selection, or B-roll changes. The playhead and guides live on
  an overlay layer, so scrubbing no longer reconstructs every clip.
- **Background preview rendering.** `POST /preview?background=true` starts a
  worker with progress, cancellation, and `GET /preview/status`. The UI shows
  the percentage and can cancel.
- **Burned titles.** `titles.plan` writes `titles.ass`; MP4 previews and
  exports apply title cards and speaker lower thirds.
- **Audio master in the render path.** `audio.master` writes
  `audio/master-filters.json`; previews apply the same high-pass, denoise, and
  EBU R128 chain to the mixed timeline audio.
- **Color/LUT step.** `color.grade` writes deterministic `eq` and optional
  `.cube` LUT filters consumed by MP4 previews.
- **Multi-entry B-roll rendering.** Every approved B-roll entry is overlaid in
  order instead of only the first one.
- **Per-clip style editing.** Timeline API and inspector now edit transitions,
  transition length, scale, position, and audio fade in/out.
- **Editable playhead timecode** and persisted clip style revisioning.
- **Isolated flow loops.** `flow.loop` over files gives each item its own
  source, output, artifacts, warnings, and Shorts.
- **Provider fallbacks for LLM, ASR, TTS, and vision.** The configured chain is
  used when no explicit endpoint is supplied.
- **Recipe automation.** Persistent `once`, `interval`, and `watch` schedules
  with a 20-second local scheduler, run-now, status, and errors.
- **Review approval and thumbnail A/B.** Persist approval/comments and the
  selected thumbnail variant; the timeline shows both deliverables.
- **Resumable model downloads.** Partial files are hashed and resumed with HTTP
  Range; statuses survive a restart as `interrupted`.

### Validation

- 455 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 19 Playwright tests passed.

### Notes

- Distribution, signing, macOS packaging, and onedir builds remain out of
  scope.
- Manual NLE QA, multicam editing beyond split-screen, and frame-accurate
  multi-select dragging remain future work.

## [0.67.0] - 2026-10-23

### Added

- **Professional canvas timeline.** Konva ruler, tracks, clip drag with
  snapping, trim handles, split, delete, ripple delete, zoom, fit, playhead
  scrubbing, and keyboard shortcuts.
- **Synced preview and waveform.** MP4 preview and wavesurfer.js waveform both
  seek with the timeline playhead; on-demand 540p proxy rendering.
- **Undo and redo.** Every edit records `timeline_history.json`; the API exposes
  `POST /timeline/undo` and `/timeline/redo`.
- **B-roll approval.** Approve, reject, and reorder planned B-roll per Short;
  persisted in `broll_approval.json` and consumed by the Shorts renderer.
- **Persistent providers.** `providers.json` with capability defaults, secret
  environment names, connection tests, and ordered fallback chains. The job
  runner uses the LLM provider chain when no explicit base URL is set.
- **Model download manager.** Background downloads with progress, cancellation,
  checksum verification, and status polling.
- **Executable flow nodes.** `flow.conditional`, `flow.loop`, and
  `flow.subflow` run real nested steps or referenced recipes.
- **Content depth.** Real `audio.master` (high-pass, FFT denoise, EBU R128),
  `titles.plan` (title cards and speaker lower thirds), `analytics.import`
  (CSV normalization), `review.queue` (pre-publish checklist), and multi-variant
  thumbnails.
- **Top-of-page errors.** A shared sticky `ErrorBanner` with alert semantics,
  copy diagnostics, and dismissal is used across every panel. Footer error
  blocks are gone.

### Removed

- Legacy project/module routes, `ProjectStore`, module registry, legacy planning
  runner, and their tests.
- Legacy rack UI: module cards, Studio panel, project templates screen, caption
  preview, asset managers embedded in the rack, and dead configuration state.
- The rack navigation tabs and the global run form. Recipes are the only
  execution path; the filesystem picker remains.

### Changed

- `PATCH /api/v1/jobs/{id}/timeline` accepts `trim`, `move`, `delete`, `split`,
  and `ripple`, returns undo/redo availability, and records history.
- Timeline responses include revision, FPS, undo/redo state, and B-roll
  approvals.
- UI version is 0.67.0 and is checked against the server version at runtime.

### Validation

- 448 Python tests passed.
- 7 media tests passed, 1 skipped.
- 13 Vitest tests passed.
- 18 Playwright tests passed.

### Notes

- Distribution, code signing, macOS packaging, and onedir builds remain out of
  scope.
- Face reframing, color/LUT, multicam, and manual NLE QA remain future work.

## [0.62.0] - 2026-10-23

### Added

- **Timeline editing foundation.** Trim, move, and delete clips through
  `PATCH /api/v1/jobs/{id}/timeline`; state revision increments and a re-render
  warning is returned.
- Timeline clip selection and edit controls.
- Caption editing remains available.
- Provider connection test, services doctor, model capability groups, recipe
  history/templates, flow-node bypasses, storyboard/thumbnail nodes.
- Legacy New project/ProjectTemplateManager removed from settings pages.

### Notes

- Full drag/trim handles, B-roll approval, provider persistence/fallback,
  scheduler, analytics, and audio master remain future work.
- 459 Python tests, 8 media tests, 14 Vitest tests, and 15 Playwright tests pass.
- Distribution remains out of scope.

## [0.57.0] - 2026-10-23

### Added

- **Recipe template gallery** with search and built-in/user recipes.
- Final recipe-management polish: Save as, version history, restore, and
  templates in one place.
- Timeline caption editing and implemented storyboard/thumbnail nodes from the
  0.56 work.
- Settings pages cleanup, provider connection test, services doctor, and models
  grouped by capability from the 0.54 work.

### Notes

- 459 Python tests, 8 media tests, 14 Vitest tests, and 15 Playwright tests pass.
- Distribution remains out of scope.

## [0.56.0] - 2026-10-23

### Added

- **Timeline caption editing.** Clicking a caption opens an editor and writes
  the new text back to `project_state.json`.
- `PATCH /api/v1/jobs/{id}/captions/{sentence_id}`.
- **Storyboard node** now writes `storyboard.json` from the validated timeline,
  captions, Shorts, and B-roll plan.
- **Thumbnail node** now renders a real thumbnail frame from the source.
- Timeline selection state and save feedback.

### Notes

- 459 Python tests, 8 media tests, 14 Vitest tests, and 14 Playwright tests pass.
- Timeline drag/trim is still pending.
- Distribution remains out of scope.

## [0.55.0] - 2026-10-23

### Added

- **Recipe version history.** Saving a recipe snapshots the previous JSON; the
  API can list and restore versions.
- **Save as** in the recipe header for forks/duplicates.
- **History modal** with restore.
- Planned control-flow nodes: `flow.conditional`, `flow.loop`, `flow.subflow`.
- 458 Python tests and 14 Playwright tests pass.

## [0.54.0] - 2026-10-23

### Changed

- Removed the legacy **New project** card and **ProjectTemplateManager** from
  Models/Services/Providers.
- Added a provider connection test:
  - base URL;
  - secret env name;
  - path;
  - HTTP status;
  - secret presence.
- API: `POST /api/v1/providers/test`.
- Provider page now separates policy from the collapsed capability catalog.
- Models page downloads are explicit and decoupled from the external-provider
  toggle.
- Services page has Doctor diagnostics and destructive-action confirmations.

### Notes

- 457 Python tests, 8 media tests, 14 Vitest tests, and 14 Playwright tests pass.
- Distribution remains out of scope.

## [0.53.0] - 2026-10-23

### Changed

- **Models page** now groups by capability and shows used-by steps, license,
  source, installed size, and explicit downloads. Model download is decoupled
  from the external-provider toggle.
- **Services page** has a Doctor/diagnostics panel, destructive-action
  confirmations, and bounded cache/disk reporting.
- **Providers page** separates policy from the capability catalog; the catalog
  is collapsed, searchable, filterable, and hides API/MCP details by default.
- Added `GET /api/v1/system/doctor`.
- Model manifest JSON includes capability, used_by, license, and source.

### Notes

- Provider connection tests and per-provider secret forms are still pending.
- 456 Python tests, 8 media tests, 14 Vitest tests, and 14 Playwright tests pass.
- Distribution remains out of scope.

## [0.52.0] - 2026-10-23

### Added

- **Recipes-first navigation.** Speech, Edit, Shorts, Studio, and Export were
  removed from the top-level UI; Recipes is the execution surface.
- **Content-cycle nodes.** Idea, research, script, storyboard, asset index,
  audio master, titles, thumbnail, publish, analytics, and review.
- **Implementation status.** New steps expose `status`, `icon`, `color`, and
  `bypass`; planned nodes show a dashed card and are skipped by the runner.
- **Asset library.** Scan local folders, search by name/tag/kind, edit tags,
  view license metadata, download, and remove entries.
- **Read-only timeline.** Video, audio, captions, B-roll, playhead, and preview
  from a successful job.
- New `content_cycle` built-in recipe with implemented and bypassed nodes.
- UI tests for the Assets and Timeline tabs.

### Notes

- The legacy rack code is no longer reachable from the UI; its backend routes
  remain for compatibility.
- 459 Python tests, 8 media tests, 14 Vitest tests, and 14 Playwright tests pass.
- Distribution remains out of scope.

## [0.51.0] - 2026-10-23

### Added

- **Per-step logs.** Recipe nodes have a Logs action that opens the log lines for
  that step from the current job.
- Final editor/scale polish for the 0.49–0.51 sequence.
- UI build guard from 0.49 keeps future releases from bundling a stale UI.

### Notes

- 452 Python tests, 8 media tests, 14 Vitest tests, and 12 Playwright tests pass.
- Kdenlive exact cross-dissolve and manual NLE QA remain pending.
- Distribution remains out of scope.

## [0.50.0] - 2026-10-23

### Added

- **Local pyannote auto-detection.** If the Models catalog installed the model,
  `audio.diarize` uses it when `model_path` is the default Hugging Face id.
- **Streaming Pexels downloads.** Stock clips are written chunk-by-chunk to a
  `.part` file instead of being buffered entirely in memory.
- **Melt plugin diagnostics.** `melt_check.py` reports failed filter/transition
  plugin loads separately from the render verdict.

### Notes

- 452 Python tests, 8 media tests, 14 Vitest tests, and 12 Playwright tests pass.
- Exact Kdenlive cross-dissolve and manual NLE QA remain pending.
- Distribution remains out of scope.

## [0.49.0] - 2026-10-23

### Added

- **Cycle prevention in the canvas.** New edges that would create a cycle are
  rejected immediately.
- **Undo/redo** for structural edits and node drags.
- **Array fields** render as JSON textareas with inline parse validation.
- **UI build guard.** `build_portable.py` rebuilds the Svelte UI and refuses a
  stale `ui/build/index.html` whose version differs from `version.ts`.
- Fixed the 0.48 local release mismatch where the server was 0.48.0 and the
  bundled UI was 0.34.0.

### Notes

- Node width remains a cycle control, not drag-resize.
- 452 Python tests, 8 media tests, 14 Vitest tests, and 12 Playwright tests pass.

## [0.48.0] - 2026-10-23

### Added

- **Pagination.** Jobs, batches, and persisted run history accept `limit` and
  `offset` and return `total`.
- **Batch history UI.** The batch modal lists persisted batches and loads them.
- **Proxy preview UI.** Successful jobs can generate and play the 540p proxy.
- **Viewport and node width persistence** in the recipe canvas.
- Tests for history pagination, batch pagination, and job listing.

### Notes

- Arrays and deeply nested objects still use the advanced JSON editor.
- Kdenlive cross-dissolve and manual NLE QA remain pending.
- 452 Python tests, 8 media tests, 14 Vitest tests, and 10 Playwright tests pass.
- Distribution work remains out of scope.

## [0.47.0] - 2026-10-23

### Added

- **Saved viewport.** The recipe canvas restores the persisted pan/zoom and saves
  viewport changes.
- **Node width cycling.** Expanded nodes cycle between compact, medium, and wide
  widths; the choice is persisted.
- **Proxy preview in the UI.** A 540p proxy can be generated from a successful
  job and played inline.
- **Persisted batch history.** The batch modal lists stored batches and loads
  them.
- URL and schema-pattern validation for inline fields.

### Notes

- Arrays and deeply nested objects still fall back to the advanced JSON editor.
- 449 Python tests, 8 media tests, 14 Vitest tests, and 10 Playwright tests pass.

## [0.46.0] - 2026-10-23

### Added

- **pyannote model downloader.** The Models catalog can install
  `pyannote/speaker-diarization-3.1` through `huggingface_hub`, using
  `HF_TOKEN` when the repository is gated.
- Installed model detection checks for `config.yaml`.
- Mocked install test for the Hugging Face path.

### Notes

- Real pyannote inference still requires the `diarization` extra and model
  access; the adapter remains lazy.
- Kdenlive cross-dissolve and manual NLE import QA remain pending.
- 449 Python tests, 8 media tests, 14 Vitest tests, and 8 Playwright tests pass.

## [0.45.0] - 2026-10-23

### Added

- **Preview proxy.** `POST /api/v1/jobs/{id}/preview` writes a 540p
  H.264/AAC proxy, served by `GET /api/v1/jobs/{id}/preview/file`.
- **Global cache pruning.** `prune_cache` trims analysis entries by age and
  total size; exposed through `videoflow recipe cache prune --global-cache` and
  the maintenance API.
- **Engine cleanup.** Removed the unimplemented `PipelineRunner.execute`
  scaffold; legacy planning remains, execution belongs to the recipe engine.
- Tests for the preview proxy and global cache pruning.

### Notes

- Preview is generated on demand; it is not automatically created after every
  render.
- 448 Python tests, 8 media tests, 14 Vitest tests, and 8 Playwright tests pass.
- Distribution work remains out of scope.

## [0.44.0] - 2026-10-23

### Added

- **Second-source audio mix.** `shorts.render.mix_second_audio` mixes the second
  split-screen source with the primary audio, with a UI checkbox.
- **Stable Pexels cache.** Stock downloads are keyed by the source URL hash, so
  repeated plans reuse the same file instead of re-downloading.
- B-roll plan remains auditable with provider, license, attribution, and source
  URL.

### Notes

- The second source is still operator-supplied; face detection and automatic
  source assignment remain future work.
- pyannote and Pexels still need real model/API validation.
- 445 Python tests, 14 Vitest tests, and 8 Playwright tests pass.

## [0.43.0] - 2026-10-23

### Added

- **Inline recipe nodes.** Each node expands into schema-derived fields with
  labels, descriptions, validation, enums, booleans, numbers, colors and path
  pickers.
- **Saved canvas.** Recipe JSON carries optional `ui` layout metadata:
  positions, expanded/pinned state, width, and viewport. UI-only changes do not
  invalidate checkpoints.
- **Autosave layout.** Dragging or pinning a node saves the recipe layout after a
  short debounce. `Auto layout` resets positions.
- **Per-step progress.** `StepIO` reports local progress; jobs expose
  `step_progress`; each node shows state and percentage.
- **Field validation.** Drafts remain editable, but Run is blocked while fields
  have errors. Server validation remains authoritative.
- Playwright coverage for saved inline layout and direct node edits.

### Notes

- 445 Python tests, 14 Vitest tests, and 8 Playwright tests pass.

## [0.42.0] - 2026-10-23

### Added

- **MLT/Kdenlive render smoke.** `scripts/melt_check.py` renders a generated
  Kdenlive/MLT project with `melt` and returns a JSON verdict.
- A media test builds a real two-cut project, exports Kdenlive, and renders it
  with `melt` when available.
- CI installs `melt` and runs the media suite.
- Final Windows, AppImage, Linux, and SBOM assets are produced by the tag
  release workflow.

### Notes

- The exact Kdenlive cross-dissolve remains a limitation; the generated project
  uses affine opacity/volume fades.
- Manual Resolve/Premiere/Kdenlive import QA remains pending.
- 443 Python tests, 8 media tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.41.0] - 2026-10-23

### Added

- **Inline preview.** MP4 artifacts render in the recipe result panel, and
  rendered Shorts get video previews.
- **Artifact serving API.**
  - `GET /api/v1/jobs/{id}/artifacts/{name}`.
  - `GET /api/v1/jobs/{id}/shorts/{index}/file`.
  - Both paths are constrained to the job output directory.
- API tests for artifact and Short file serving.

### Notes

- Previews use the rendered file; there is no low-res proxy yet.
- 443 Python tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.40.0] - 2026-10-23

### Added

- **Job persistence.** `JobManager` writes each job as JSON under the VideoFlow
  home and reloads it on restart. Queued/running jobs become `failed` with
  `job_interrupted`, so the API never reports a dead job as live.
- **Batch resume.** `POST /api/v1/batches/{id}/resume` and the batch modal
  restart failed/cancelled batches, skipping items already succeeded.
- **Shared persistence pattern** for jobs and batches: atomic JSON writes,
  restart reload, interrupted-state recovery.
- Tests for job restart, interrupted jobs, and batch resume.

### Notes

- The legacy `PipelineRunner.execute` contract remains an xfail; planning is
  live, and the recipe engine is the execution path.
- 442 Python tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.39.0] - 2026-10-23

### Added

- **Tag-driven release workflow.** `v*` tags build Linux, AppImage, and Windows
  artifacts, generate an SBOM, stage checksums, and publish the GitHub release.
- **Windows smoke test.** The Windows runner executes `version`, `doctor`, and
  `demo` before uploading the executable.
- **Media tests in CI.** `pytest -m media --no-cov` now runs on Ubuntu.
- **SBOM.** `scripts/generate_sbom.py` writes a CycloneDX-style JSON SBOM; the
  release includes `sbom.json`.
- **Automatic retention.** Successful recipe runs prune checkpoints beyond 200
  and run history beyond 30. Opt out with `VIDEOWFLOW_PRUNE_AFTER_RUN=0`.
- Fixed the media API test to force the FFmpeg VAD path instead of depending on
  Silero's speech classification.

### Notes

- 439 Python, 14 Vitest, and 6 Playwright tests pass.
- Media suite: 7 passing.

## [0.38.0] - 2026-10-23

### Added

- **Two-source split-screen.** `shorts.render.second_source_path` renders the
  left panel from the main source and the right panel from a second angle.
  Without a second source, the same-source two-panel layout remains.
- UI control and file picker for the second split-screen source.
- Repository policy test: project configuration and test data are JSON; only
  GitHub Actions workflows may be YAML.
- Playwright coverage for the second-source control.
- Final Windows PE workflow run and release attachment.

### Notes

- Exact Kdenlive cross-dissolve is still not validated; Kdenlive uses the
  affine opacity/volume transition fades.
- Manual Resolve/Premiere/Kdenlive import QA remains pending.
- 439 Python tests, 14 Vitest tests, and 6 Playwright tests pass.

## [0.37.0] - 2026-10-22

### Added

- **Schema-driven inspector.** Primitive parameters are rendered from each
  step's `params_schema` (boolean, number, enum, text), not only from the
  hand-written quick controls.
- **NLE validation in the UI.** A Validate action calls
  `POST /api/v1/exports/validate` and shows per-format status, counts, errors,
  and warnings.
- **B-roll plan viewer.** Job results expose `broll_plan`, and the UI shows the
  provider, license, and path for each planned clip.
- **Persistent batch history.** Batch JSON is written to the VideoFlow home,
  reloaded on restart, and interrupted batches are marked failed.
- Playwright now covers schema fields and the NLE validation modal.
- JSON-only configuration policy documented for project data and tests.

### Notes

- GitHub Actions still uses YAML because the platform requires it.
- 437 Python tests and 5 Playwright tests pass.

## [0.36.0] - 2026-10-22

### Added

- **Schema gates.** Recipes and project state now pass through explicit
  `schema_version` migration functions. Missing optional fields in older recipe
  JSON are filled before validation; future versions fail with a typed error.
- **Output maintenance.** `prune_output` removes old checkpoints beyond a keep
  count, stale B-roll cache files, and trims run history.
- CLI: `videoflow recipe cache prune --output ... --keep-steps ... --keep-runs ...`.
- API: `POST /api/v1/maintenance/prune`.
- Tests for migrations, malformed/future versions, checkpoint pruning, history
  trimming, and dry runs.

### Notes

- Checkpoints are still output-local and can be rebuilt; pruning never touches
  source media or export artifacts.
- 434 Python tests pass.

## [0.35.0] - 2026-10-22

### Added

- **Failed-run diagnostics.** Recipe failures write `work/failure.json` with the
  stage, error payload, FFmpeg command, stderr tail, and the last 200 log lines.
- **Failed runs in history.** `run-history.json` now records `failed` and
  `cancelled` runs with their error, so the UI survives restarts and shows them.
- **Playwright E2E.** Installed `@playwright/test`, added a JSON reporter, and
  covered the recipe graph, inspector transition controls, step palette, and
  persisted run-history browser.
- Refactored job history recording into one path for success, failure, and
  cancellation.
- `docs/testing.md` now reflects CI and Playwright.

### Notes

- GitHub Actions still needs a Playwright step; this release wires the local
  command and JSON report first.
- 427 Python tests, 14 Vitest tests, and 3 Playwright tests pass.

## [0.34.0] - 2026-10-22

### Added

- **NLE structural validation.** `scripts/validate_nle.py` and
  `POST /api/v1/exports/validate` parse FCPXML, XMEML, and Kdenlive exports and
  report clips, transitions, keyframes, effects, and affine filters.
- **Manual NLE checklist** in `docs/nle-qa.md`.
- **Legacy module rerun.** The project module route plans the rack graph,
  returns a cached no-op, or starts the full project pipeline. It no longer
  returns `501`.
- **Windows PE in releases.** The Windows workflow downloads a PE32+ x86-64
  executable and the release script attaches it when present.
- CI can be dispatched manually and runs Python and UI checks.

### Notes

- The legacy module route reruns the full graph; it does not yet execute one
  module in isolation. Recipe steps remain the checkpointed path.
- Resolve, Premiere, and Kdenlive are not installed here, so manual import QA is
  still pending. Automated XML validation passes.
- The Windows binary is unsigned; SmartScreen may warn.
- 426 Python tests and 14 UI tests pass.

## [0.33.0] - 2026-10-22

### Added

- **Optional model-based diarization.** `audio.diarize` supports
  `method: "pyannote"` with `model_path`, `device`, and an HF token environment
  variable. It falls back to the pause heuristic by default.
- **Pexels B-roll provider.** `broll.plan` can search and download portrait
  stock clips using `PEXELS_API_KEY`; local assets remain the default.
- **Dialogue split-screen.** `shorts.reframe` marks multi-speaker clips for the
  two-panel layout, and the renderer supports per-panel focus and zoom.
- B-roll plans now include provider, license, attribution, and source URL.
- UI controls for pyannote, Pexels, dialogue split, and panel focus/zoom.
- Optional `diarization` dependency extra.

### Notes

- Pyannote is not installed in this build; the adapter is lazy and tested with a
  fake pipeline plus the heuristic fallback.
- Pexels is opt-in and requires an API key; local B-roll remains fully offline.

## [0.32.0] - 2026-10-22

### Added

- **Kdenlive transforms and keyframes.** Video entries receive an MLT `affine`
  filter with static geometry or `transition.rect` keyframes.
- **Kdenlive transition fades.** Clip transitions add opacity keyframes and
  volume ramps in the MLT project.
- **Recipe inspector quick controls** for transition frames/type, progressive
  zoom, speaker turns, B-roll directory, split-screen, B-roll application, and
  caption speaker colors.
- **Run history browser** in the Recipes tab, with persisted runs and comparison.
- **Piper provider controls** in the Short editor, with binary and model path.
- README, exporter docs, and capability status updated.

### Notes

- Kdenlive crossfades are emitted as opacity/volume fades rather than a validated
  exact cross-dissolve; Kdenlive itself is not available on this build host.
- 419 Python tests and 14 UI tests pass.

## [0.31.0] - 2026-10-22

### Added

- **Heuristic speaker turns.** `audio.diarize` assigns speaker ids by pause
  length. Captions use `CaptionStyle.speaker_colors` for per-speaker colors.
- **Local B-roll.** `broll.plan` matches files in a local asset directory to
  selected Shorts and writes `broll.json`; `shorts.render` applies full-frame
  B-roll overlays.
- **Split-screen Shorts.** `shorts.render` accepts `split_screen` and renders a
  two-panel vertical frame.
- **Local Piper TTS.** The voice-over route accepts `provider: "piper"` with a
  binary and voice model path, in addition to OpenAI-compatible TTS.
- Capability manifest entries for transitions, speaker turns, B-roll,
  split-screen, and local TTS.

### Notes

- Diarization is heuristic, not model-based speaker identification.
- B-roll is local-asset matching, not a stock-video search service.
- Kdenlive parity for transforms and transitions remains pending.

## [0.30.0] - 2026-10-22

### Added

- **Persistent run history.** Successful recipe runs append a compact record to
  `<output>/work/run-history.json`; `GET /api/v1/runs?output=...` exposes it.
  The comparison modal uses this history, so it survives a server restart.
- **GitHub Actions CI.** Linux tests and UI checks run on push and pull request.
- **Windows portable build workflow.** A `windows-latest` workflow builds and
  uploads `videoflow.exe`.
- **Optional onedir build.** `scripts/build_portable.py --onedir` uses PyInstaller
  `COLLECT` instead of a onefile executable.

## [0.29.0] - 2026-10-22

### Added

- **Clip transitions.** `VideoSegment.transition_out` carries a
  `Transition` with `crossfade` or `fade_to_black`, duration, and audio flag.
- `edit.timeline` accepts `transition_frames` and `transition_type`.
- **FCPXML** emits a `transition` element between clips.
- **XMEML** emits a video `transitionitem` with Cross Dissolve/Fade to Black.
- **MP4** uses `xfade`/`acrossfade` for crossfades and video/audio fades for
  fade-to-black.
- Project-state schema updated for transitions.

### Notes

- Kdenlive does not apply clip transforms or per-cut transitions yet.
- The transition duration reduces the MP4 duration for crossfades because the
  clips overlap, as expected.

## [0.28.0] - 2026-10-22

### Added

- **Progressive zoom keyframes.** `Transform` now carries normalized scale
  keyframes. `progressive_zoom` generates two smooth keyframes (minimum scale
  to punch-in scale) for alternating clips.
- **FCPXML keyframes.** `adjust-transform` emits a keyframed `scale` parameter
  with clip-relative rational times.
- **XMEML keyframes.** Basic Motion scale emits `keyframe` entries with
  clip-relative frame positions.
- **MP4 keyframes.** The direct renderer uses `zoompan` for clips with
  keyframes, keeping the output dimensions stable.
- Project state schema updated for `TransformKeyframe`.

### Notes

- Kdenlive does not apply clip transforms yet, so keyframes are not represented
  there.
- Transitions between clips remain the next editing pass.

## [0.27.0] - 2026-10-22

### Added

- **Run comparison.** After a successful recipe run, the UI finds the previous
  successful job for the same output and recipe and offers a comparison modal.
  It shows duration, cached/executed counts, warnings, and a per-step table with
  previous/current status and elapsed milliseconds.
- The comparison uses the normal job history; no new persistent store is
  required.

### Notes

- Keyframed progressive zooms and video transitions remain the next creative
  editing pass. This release focuses on run observability.

## [0.26.0] - 2026-10-22

### Added

- **Direct main-timeline MP4 render.** `export.nle` accepts `mp4` as a target.
  The exporter builds a filter graph from the validated timeline, applies
  J/L-cut audio ranges, fades, and static transforms, and writes H.264/AAC with
  `+faststart`. The legacy job form and recipe editor expose the target.
- **Folder batches.** `videoflow recipe batch`, `POST /api/v1/batches`,
  `videoflow_run_batch`, `videoflow_get_batch`, and `videoflow_cancel_batch`
  process a folder one file at a time. Each item is a normal job with its own
  output folder, progress, cancellation, logs, and recipe checkpoints.
- **Batch UI.** The Recipes tab has a **Batch** modal with folder pickers,
  recursive mode, extension filter, item-level progress, and cancel.
- **Capability manifest entries** for direct MP4 and folder batches.

### Changed

- `ExportParams.targets` and `NewJobRequest.export_targets` accept `mp4`.
- `FFmpegAdapter.render` is implemented with a one-hour render timeout.
- Built-in recipe validation now enforces required upstream step types.

### Validation

- 405 Python tests passed; 14 UI tests passed.
- Real FFmpeg media rendered through the timeline filter graph and was probed
  back at the source dimensions.
- A two-file batch completed both items into separate output folders.

## [0.25.0] - 2026-10-22

### Added

- **Per-step checkpoints.** Every successful recipe step writes
  `work/steps/<id>/manifest.json` and `snapshot.json`. A fingerprint covers the
  step type/version, validated parameters, source fingerprint, and upstream
  step hashes. Matching steps are reused across runs in the same output
  directory, and file-producing steps verify that their outputs still exist.
- **Step-scoped runs.** `POST /api/v1/steps/{step_id}/run`,
  `videoflow recipe step ...`, and the MCP tool `videoflow_run_step` execute a
  step and its dependency closure, then stop.
- **Resume controls.** `videoflow recipe run|step --force` ignores
  checkpoints; the Recipes Config modal has a reuse-checkpoints switch.
- **Per-node execution state.** The graph shows cached, executed, running, and
  failed nodes. The inspector has **Run to here**.
- **Step run reporting.** Job results and `run.json` expose `step_runs` with
  status, elapsed time, fingerprint, and outputs.
- **Dependency validation.** Recipes are rejected when a step's declared
  upstream types are missing, preventing steps from running with absent VAD or
  transcript context.

### Fixed

- `retakes.cull` now explicitly requires `audio.vad` in addition to the
  transcript, so partial runs cannot subtract culls from empty speech.
- Built-in Shorts recipes place NLE export after Shorts rendering.

## [0.24.0] - 2026-10-22

### Added

- **Independent Shorts steps.** `shorts.select`, `shorts.reframe`,
  `shorts.captions`, and `shorts.render` are separate nodes. Reframe tracking
  and ASS caption generation no longer happen inside selection/render.
- **Recipe analysis cache.** `audio.vad` and local/HTTP `transcribe` results are
  cached by source PCM digest plus step parameters under
  `<videoflow-home>/cache/recipe-v1/`. The cache is shared across output
  directories. `videoflow recipe cache path|clear` inspects or clears it;
  `VIDEOWFLOW_RECIPE_CACHE=0` disables it.
- **Cache hit/miss reporting.** `run.json`, job results, and `PipelineContext`
  expose `cache_hits` and `cache_misses`.
- **Full-width recipe canvas.** The Recipes tab now spans the whole content
  area and hides the legacy run-summary sidebar while active.
- **Collapsible recipe controls.** The step inspector is an overlay that opens
  on node click; the step palette is a filterable popover; recipe settings and
  the full recipe/step JSON editor are modal dialogs with a large text area.

### Changed

- The built-in Shorts recipes now run `shorts.reframe` and `shorts.captions`
  explicitly before `shorts.render`.
- `shorts.select` no longer tracks faces. If a recipe sets a non-center
  `reframe_mode` on selection, it emits a warning and leaves tracking to
  `shorts.reframe`.

### Fixed

- Added a test-isolation home so recipe cache entries never touch the
  developer's real `~/.videoflow` directory.

## [0.23.1] - 2026-10-22

### Fixed

- Recipe path parameters are now resolved through the same allowlist jail as
  media, output, and transcript paths. This covers `srt_path` and the
  overlay/music/intro/outro assets of `shorts.render` in REST and MCP runs.
- Built-in Shorts recipes now depend on the retakes step, so selection uses the
  same cull decisions as the main timeline instead of racing it.
- Operator recipes under the VideoFlow home directory override built-in recipes
  with the same id, and recipe ids are validated before any filesystem lookup.

## [0.23.0] - 2026-10-22

### Added

- **Recipe engine v1.** Recipes are versioned DAGs of typed steps with
  explicit dependencies, stable ids, parameter schemas, progress, cancellation,
  and per-step hashes. The engine validates duplicate ids, unknown step types,
  missing dependencies, disabled dependencies, and cycles before execution.
- **Step registry.** Ingest, voice detection, transcription, retakes, timeline,
  Shorts selection, Shorts rendering, and NLE export are independently
  invocable. The legacy pipeline remains available and is covered by a parity
  test against the recipe path.
- **Recipes tab, first in the workspace.** A Svelte Flow canvas edits the DAG,
  exposes JSON parameters per node, loads built-in recipes, validates, saves,
  downloads, and runs jobs with live progress.
- **Recipe API.** `GET /api/v1/steps`, `GET /api/v1/recipes`,
  `GET /api/v1/recipes/{id}`, `PUT /api/v1/recipes/{id}`,
  `POST /api/v1/recipes/validate`, and `POST /api/v1/recipes/run`.
- **Recipe MCP tools.** `videoflow_list_steps`, `videoflow_list_recipes`,
  `videoflow_get_recipe`, `videoflow_validate_recipe`,
  `videoflow_save_recipe`, `videoflow_run_recipe`, and
  `videoflow_run_recipe_inline`.
- **Recipe CLI.** `videoflow recipe list|steps|show|validate|run`.
- **Built-in recipes and examples.** `youtube_talking_head`,
  `viral_shorts_batch`, and `full_podcast_curation`, mirrored under `recipes/`.
- **LLM router.** OpenAI-compatible local/cloud endpoints are the default; an
  opt-in OpenCode CLI adapter adds timeouts, a non-shell subprocess, output
  limits, and strict JSON parsing. Secrets are stored by environment variable
  name, never inside recipes.
- **Recipe JSON Schema** at `schemas/recipe.schema.json`.

### Notes

- The visual editor is additive: the existing Speech, Edit, Shorts, Studio,
  Export, Models, Services, and Providers tabs remain available.
- The v1 recipe scope is the current pipeline. B-roll, TTS, and new vision
  models remain future steps.

## [0.22.3] - 2026-10-21

### Fixed

- Moved the workspace tabs (Speech, Edit, Shorts, Studio, Export, Models,
  Services, Providers) directly under the header as a sticky navigation bar.
  Shorts, Models, and Services no longer disappear below the New project card.
- Removed a duplicated connection banner inside the header that pushed the page
  down and made the tab bar harder to find.
- Added cache-control headers: `index.html` and `/` are `no-store`; hashed
  `_app/immutable` assets are immutable; other UI assets are revalidated.
- The browser now opens with `?v=<version>`, preventing an old UI bundle from
  being reused after an update.
- Added a UI/server version mismatch banner with a **Reload UI** action.
- Added a per-port startup lock so double-clicking the AppImage several times
  does not start competing servers; later launches wait for health and open the
  existing UI.
- Verified the AppImage starts from a detached, no-terminal session, keeps
  running, serves the UI, and exposes the Services tab.

## [0.22.2] - 2026-10-21

### Fixed

- Starting a new VideoFlow build no longer reuses an older service on the same
  port. The launcher reads `/health`, compares versions, stops the old
  VideoFlow process tree, waits for the port, and starts the current version.
  This removes the "already running" loop that kept a 0.20.0 service alive.
- Discovery now finds VideoFlow `serve`/`mcp`/`desktop` processes through
  `/proc`, including AppImage-mounted binaries and their parent processes.
- Added a **Services** tab with the current PID, port, version, URL, other
  VideoFlow services, per-process Stop, Stop all others, Restart current, and
  Stop current.
- The Services tab shows the server log and its path; startup, version
  replacement, cleanup, restart, and crashes are appended to
  `videoflow-data/logs/server.log`.
- `videoflow status` now lists discovered services in addition to the PID file.
- Cleanup stops port-owning children before launchers/parents and falls back to
  SIGKILL when SIGTERM does not finish in time.

## [0.22.1] - 2026-10-21

### Fixed

- The local file browser no longer turns a damaged or out-of-range file
  timestamp, unreadable entry, or deleted current directory into an HTTP 500.
  Failed entries are skipped and the picker offers "Open Home folder".
- Service lifecycle: `serve` keeps the executable running, writes
  `server.pid`, detects an already-running instance, and can be managed with
  `videoflow status`, `videoflow stop`, and `videoflow restart`.
- The rack header now has **Restart service** and **Stop service** buttons.
  Restart reuses the in-memory job manager and recreates the MCP session.
- The AppImage starts in the user's home directory and prints explicit
  instructions for keeping the service running or stopping it.

## [0.22.0] - 2026-10-21

### Added

- OpenAI-compatible multimodal Short analysis through
  `POST /api/v1/jobs/{job_id}/shorts/{index}/analyze/llm` and
  `videoflow_analyze_short_llm`. Frames are sampled locally, sent only when
  external services are enabled, and the result is persisted in `shorts.json`.
- A separate Studio tab with AI Analysis, Timeline, Keyframes, Tracks, and
  Transitions sections. AI Analysis runs vision analysis; Timeline opens the
  per-Short editor; the other sections expose reframe, track, and transition
  state.
- LLM emoji captions: `POST /api/v1/jobs/{job_id}/shorts/{index}/captions/emoji`
  and `videoflow_generate_short_emoji` generate a validated emoji map and
  re-render the Short with it.
- Optional model downloads through `GET /api/v1/models`,
  `POST /api/v1/models/{id}/install`, `DELETE /api/v1/models/{id}`, the Models
  tab, and three MCP tools. Downloads are checksum-verified and stored under
  the portable home directory.
- Lean portable builds: speech model weights are excluded unless
  `VIDEOWFLOW_BUNDLE_MODELS=1` or `scripts/build_portable.py --with-models` is
  used. Downloaded models are resolved at runtime without rebuilding.
- 30 transcription language codes across CLI/API/MCP/UI, including auto-detect.
- Short render resolution selection: 1080, 1440, or 2160 short-edge. 4K renders
  as 2160x3840 vertical, 2160x2160 square, or 3840x2160 landscape.

- Tabbed rack navigation: Speech, Edit, Shorts, Export, and Providers. Each tab
  shows only the modules and controls that belong to that area.
- A provider/capability panel backed by `GET /api/v1/capabilities` and the
  `videoflow_list_capabilities` MCP tool. External providers are opt-in per run
  and can be blocked globally with `VIDEOWFLOW_ALLOW_EXTERNAL=0`.
- `ProvidersConfig` in project state. `allow_external_services` is persisted and
  forwarded by project runs.
- Short render aspect ratios: `9:16`, `1:1`, and `16:9`. ASS PlayRes and FFmpeg
  dimensions follow the selected aspect.
- Short source window: `shorts_source_start_sec` and `shorts_source_end_sec` in
  the CLI, API, MCP, project config, and UI.
- Duration presets in the Shorts tab and an aspect-aware caption preview.
- Per-Short editor: trim, retitle, aspect/frame size, caption overrides, and
  re-render. The API is `POST /api/v1/jobs/{job_id}/shorts/{index}/edit`, the
  MCP tool is `videoflow_edit_short`, and the rack uses Clip/Captions tabs.
- Prompt-to-Clip and reprompt for Short selection: topic focus, refinement
  context from the previous `shorts.json`, heuristic term boosts, and LLM focus.
  Exposed in CLI, API, MCP, project config, and the Shorts tab.
- Auto hook (`off`, `metadata`, `repeat`, `reorder`) and an explainable 0–100
  virality score with a per-factor breakdown. Hook/score metadata appears in
  `shorts.json` and the rack.
- Short result badges expose the selected aspect, virality score, and hook text.
- Caption profanity masking with a configurable word list/replacement.
- Optional filler-word cuts for Shorts when word timings are available.
- Deterministic social metadata (title, description, hashtags, character limits)
  for YouTube, TikTok, Instagram, and LinkedIn, exposed via API/MCP and the
  Short editor's Metadata tab.
- Caption keyword highlighting, contextual emoji mapping, and brand vocabulary
  rewriting. Empty keyword lists auto-select frequent content words.
- Custom TTF/OTF font upload with internal-family detection, a local font asset
  store, UI font picker, `fontsdir` rendering, and API/MCP access.
- Short thumbnail generator: frame extraction plus caption-style title overlay,
  persisted under `shorts/thumbs/` and exposed through API/MCP/UI.
- Optional FFmpeg speech enhancement for rendered Shorts: high-pass, FFT
  denoise, and loudness normalization, with API/MCP/UI/CLI controls.
- Watermark overlay: PNG/JPEG asset store, position/margin/width/opacity
  controls, API/MCP/UI access, and post-caption compositing.
- Background music: MP3/WAV/M4A/AAC/OGG asset store, looping bed, volume,
  fades, sidechain ducking, and AAC mix output.
- External TTS voice-over: OpenAI-compatible synthesis, environment-only API
  key, original-audio ducking, mixed MP4, API/MCP/UI controls.
- Intro/outro image cards with configurable durations, normalized size, silent
  audio, and API/MCP/UI access.
- Translation dubbing: external LLM translation, TTS synthesis, dub-only mix,
  and API/MCP/UI controls.
- Reusable brand templates bundling caption style, overlay, music, and
  intro/outro settings, with save/apply/delete and server-side job application.
- Motion-tracking reframing with frame-difference focus, optional OpenCV face
  tracking fallback, and persisted crop focus.
- Project templates and versioned config export/import for non-secret run
  options.
- Audio-energy peak analysis that boosts Short candidates and exposes peak
  counts.
- FFmpeg scene-change analysis that boosts Short candidates around visual cuts
  and exposes scene counts.
- Public URL import through yt-dlp, external-policy guarded, with API/MCP/UI
  integration and normal media probing.
- Webhook publishing and scheduling with target CRUD, generated metadata, a
  durable queue, bearer-token secret references, and a local daemon.
- Optional multimodal Short analysis: audio-emotion heuristics, visual motion
  regions, and OpenCV face statistics when installed.

### Changed

- `scripts/release.py` now keeps only the three newest `releases/v*` folders.
  `--keep N` changes the retention count, and the release output lists every
  pruned folder.
- Release staging is documented as the canonical artifact store. Generated
  `build/`, `dist/`, coverage files, and caches are cleaned after each release.
- MCP now exposes thirty-six tools and four resources.

### Docs

- Refreshed the README, module specs, testing notes, UI spec, and operator
  manuals to describe FCPXML audio fades, the caption preview, the tabbed rack,
  provider policy, Short aspect ratios, and the three-release retention policy.

### Verified

- Tests: 370 passed, 11 xfailed, 7 deselected; coverage 99.06%; ruff and mypy
  clean.
- UI: `svelte-check` reports 0 errors and 0 warnings; 13 Vitest tests and the
  production build pass.

## [0.21.2] — 2026-10-21

### Added

- The Shorts card now includes a live 9:16 caption preview. It follows the
  configured font, size, weight, italic/uppercase, primary and karaoke colors,
  outline, shadow, box, alignment, position, and animation.

### Fixed

- FCPXML/Resolve now emits audio fade edges as keyframed `adjust-volume` ramps
  on each `asset-clip`. The ramp uses the clip-relative `keyframeAnimation`
  form required by the FCPXML 1.9 DTD.
- FCPXML sequences declare the enumerated `audioRate` label (`48k`, `44.1k`, ...)
  instead of raw hertz. A generated timeline now validates against the FCPXML
  1.9 DTD.
- All three NLE artifacts now carry audio fades: xmeml transition items,
  Kdenlive volume filters, and FCPXML volume keyframes.

### Verified

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- UI: `svelte-check` reports 0 errors and 0 warnings; the production build
  succeeds with 13 Vitest tests.
- Linux and Windows binaries produced six xmeml fade items, a Kdenlive volume
  ramp, and FCPXML that validates against the official 1.9 DTD. Sizes and
  SHA-256 values are in `releases/v0.21.2/` and its `manifest.json`.

## [0.21.1] — 2026-10-21

### Fixed

- Premiere xmeml now writes single-sided `transitionitem` fades for audio
  fade-in and fade-out edges, using the Cross Fade (0 dB) audio transition.
- Kdenlive MLT audio entries now carry a keyframed `volume` filter for the same
  fades. The project still opens as a native `.kdenlive` sequence.
- FCPXML/Resolve fade transitions remain pending; the FCPXML artifact still
  carries the audio offsets but not dedicated fade elements.

### Verified

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- Linux and Windows binaries emitted six xmeml audio transition items and a
  Kdenlive volume keyframe ramp. Sizes and SHA-256 values are in
  `releases/v0.21.1/release-notes.md` and `manifest.json`.

## [0.21.0] — 2026-10-21

### Added

- Configurable zoom window: `min_scale`, `max_scale`, and `punch_in_scale` with
  validation and UI/API/MCP controls. The state model no longer hard-codes a
  1.30 maximum.
- Configurable audio fades: `fade_in_ms`, `fade_out_ms`, and `fade_curve` in the
  J/L-cut module, in addition to the existing crossfade and offset.
- Configurable Shorts selection: target count, minimum count, duration window,
  and `auto|llm|heuristic` ranking. The LLM client is created for Shorts even
  when retake culling is off, and the heuristic ranks hook/impact signals rather
  than taking the first windows.
- `videoflow run --shorts` with count/minimum/duration/selection flags, so the
  main project and vertical Shorts are produced together.
- Detailed caption/karaoke style: font family, size, weight, italic, uppercase,
  primary/highlight/outline colors, outline width, shadow color/offset/opacity,
  background box color/opacity/padding, alignment, normalized position, max
  width, animation, and word-timing fallback.
- ASS karaoke generation from word timings, with proportional and sentence
  fallbacks when an engine does not return word timestamps.
- The same caption and Shorts fields are available in the UI rack, job API,
  project config, presets, and MCP overrides. `videoflow_generate_shorts` now
  accepts `min_count` and `selection_mode`.

### Changed

- The setup card now has an explicit “Also render vertical shorts” control, and
  the “Main + Shorts” starting point makes clear that Shorts are additive.
- Shorts report a score and warning when fewer than the configured minimum can
  be selected.
- Audio fade timing/curve is now configurable and stored on the timeline. NLE
  transition elements for those fades remain a follow-up; the current exporters
  still carry the audio cut offsets rather than dedicated crossfade items.

### Verified

- Tests: 315 passed, 11 xfailed, 7 deselected; coverage 99.00%; ruff and mypy
  clean.
- UI: 0 errors/warnings, 13 Vitest tests, production build passed.
- A real source with `--shorts` produced the main project and Shorts MP4s/ASS,
  including word-timed karaoke.
- Linux binary, AppImage, and Windows PE were built and smoke-tested. Sizes and
  SHA-256 values are in `releases/v0.21.0/release-notes.md` and
  `manifest.json`.

## [0.20.1] — 2026-10-20

### Fixed

- DaVinci Resolve FCPXML 1.9/1.10 media references now use the required
  `<media-rep kind="original-media" src="..."/>` child. The old `<asset src>`
  form is FCPXML 1.8-only and could make Resolve reject or offline the timeline.
- Premiere Pro now receives xmeml version 4 with `explodedTracks`, a sequence
  UUID, `file://localhost/` path URLs, a full `<file>` definition on every
  video and audio clipitem, and explicit A/V `<link>` groups. The Basic Motion
  effect id is now `basicmotion`.
- Kdenlive now receives a native `.kdenlive` MLT XML project instead of an OTIO
  file: profile, source chain, video/audio tractors, sequence tractor, bin, and
  final tractor. OTIO remains available as a library helper, not the Kdenlive
  deliverable.

### Changed

- The Kdenlive artifact is `timeline.kdenlive`; the API/MCP target key remains
  `kdenlive`. The historical `write_otio` config key still controls this
  artifact.
- Export tests now assert the media-rep, xmeml full-file/link shape, and native
  MLT structure.

### Verified

- Tests: 310 passed, 11 xfailed, 7 deselected; coverage 99.28%; ruff and mypy
  clean.
- Linux and Windows binaries wrote all three artifacts; each was parsed back as
  FCPXML, xmeml, or MLT XML and checked for its required media links and track
  structure. AppImage smoke passed.
- Sizes and SHA-256 values are in `releases/v0.20.1/release-notes.md` and
  `manifest.json`.
- The three NLE import flows still require a manual gate in Resolve, Premiere,
  and Kdenlive; this environment does not have those applications installed.

## [0.20.0] — 2026-10-20

### Added

- A local filesystem browser for the rack: `GET /api/v1/fs/roots`,
  `GET /api/v1/fs/list`, and `POST /api/v1/fs/mkdir`, with search, file-extension
  filters, hidden-file control, breadcrumbs, writable checks, and a 2,000-entry
  ceiling.
- `GET /api/v1/media/probe`, so selecting a source shows duration, resolution,
  frame rate, audio rate, and size without running the pipeline.
- `PathPicker.svelte` with keyboard navigation, focus trapping, loading, empty,
  and typed error states. It replaces typed source, output, SRT, and model paths
  in the primary flow.
- Source selection suggests `<source-stem>-videoflow` next to the source. The
  output picker can create a folder in place.
- A redesigned project setup: numbered source/output/transcript cards, metadata
  chips, YouTube/Lecture/Shorts starting points, a collapsed advanced section, a
  clear primary action, inline validation, progress details, and transient
  success toasts.
- Pure path helpers for POSIX and Windows basenames, parents, and output
  suggestions, covered by Vitest.

### Changed

- The rack no longer requires typing an absolute path in the normal flow.
  Advanced users can still paste paths under **Advanced paths and local models**.
- The primary action is disabled until both source and output are present, and
  source/output/transcript changes keep the UI state consistent.
- The run summary keeps the same job, artifact, recent-job, inspector, and log
  behavior while adopting the updated visual hierarchy.

### Security

- The browser is restricted to `VIDEOWFLOW_ALLOWED_ROOTS`; symlinks that escape a
  root are omitted or rejected. Directory creation validates a single portable
  segment, including Windows reserved names. No media is uploaded.

### Verified

- Tests: 309 passed, 11 xfailed, 7 deselected; coverage 99.28%; ruff and mypy
  clean.
- UI `check` reports 0 errors and 0 warnings; 13 Vitest tests pass and the
  production build succeeds.
- Frozen Linux UI: selected a real 48 kHz source, showed its metadata, created
  an output folder, ran the pipeline, and wrote all three exports.
- Linux binary, AppImage, and Windows PE were built. Windows `version`, `doctor`,
  `demo`, served filesystem routes, and a real Faster-Whisper run passed under
  Wine. Sizes and SHA-256 values are in
  `releases/v0.20.0/release-notes.md` and `manifest.json`.

## [0.19.0] — 2026-10-20

### Added

- Local Faster-Whisper 1.2.1 transcription through CTranslate2, with the full
  16 kHz WAV sent to the engine, word timestamps required for the quality path,
  and exact floor/ceil conversion from word seconds to source samples.
- `TranscribeConfig.engine` with `auto`, `faster-whisper`, and `whisper.cpp`.
  `auto` prefers Faster-Whisper when the optional package and selected model are
  present, then falls back to whisper.cpp. Explicit engines fail with an
  actionable hint instead of silently downgrading.
- `--whisper-engine`, `--model-size`, `--device`, `--compute-type`,
  `--whisper-vad`, and `--faster-whisper-model` in `videoflow run`; matching job
  API fields, project run options, MCP arguments/overrides, and rack controls.
- Local CTranslate2 model discovery through `VIDEOWFLOW_FASTER_WHISPER_MODEL`,
  the frozen bundle, the executable directory, and the portable home. A model
  directory must contain `model.bin` and `config.json`; models are never
  downloaded implicitly.
- `scripts/fetch_faster_whisper.py` with the pinned
  `Systran/faster-whisper-small` revision
  `536b0662742c02347bc0e980a01041f333bce120`, per-file sizes, and SHA-256
  verification.
- `--with-faster-whisper` and `--refresh-faster-whisper` in the portable build.
  PyInstaller collects Faster-Whisper, CTranslate2, Tokenizers, PyAV, Hugging
  Face Hub, and the ~484 MB small model under `faster-whisper/small/`.
- `doctor` reports the Faster-Whisper package version, resolved model, and
  readiness.
- Unit, contract, CLI, job, API, MCP, runtime, and portable coverage for engine
  selection, fallback, explicit failures, full-WAV calls, exact timestamps, and
  model discovery.

### Changed

- `transcribe` is now an `auto` local quality path. An SRT or project transcript
  still wins, and an ASR base URL still takes precedence over both local engines.
- Transcript sources are reported distinctly as `faster-whisper`, `whisper`,
  `asr`, `srt`, or `project`.
- The optional `faster-whisper` extra pins Faster-Whisper 1.2.1 and PyAV
  `>=11,<19`; PyAV 19 removes the `metadata_errors` argument used by 1.2.1.
- Release builds bundle the model and runtime, so artifacts are substantially
  larger than 0.18.0. A build without the flag keeps the whisper.cpp fallback.

### Verified

- Tests: 301 passed, 11 xfailed, 7 deselected; coverage 99.27%; ruff and mypy
  clean; UI check, Vitest, and production build pass.
- A real 48 kHz source produced a `faster-whisper` transcript with source-sample
  word timings; `auto` selected Faster-Whisper and an explicit whisper.cpp run
  still completed. The frozen Linux API and AppImage quality paths produced the
  same result.
- Linux 0.19.0 binary, AppImage, and Windows PE were built and smoke-tested.
  Windows `version`, `doctor`, `demo`, and a real Faster-Whisper run passed under
  Wine. Sizes and SHA-256 values are in
  `releases/v0.19.0/release-notes.md` and `manifest.json`.

## [0.18.0] — 2026-10-20

### Added

- Silero VAD v5.1.2 as the quality speech detector, running through ONNX
  Runtime on the CPU with 16 kHz mono PCM, 512-sample windows, and the pinned
  `state` tensor carried between windows.
- Typed VAD engine selection: `auto` prefers Silero when the model and
  `onnxruntime` are available, `silero` requires it, and `ffmpeg` forces
  `silencedetect`. Explicit Silero failures are actionable instead of silent.
- Exact floor/ceil rescaling from 16 kHz windows to source sample spans, plus
  speech pads that are applied after retake culling and clamped to the media
  duration.
- `--vad-engine`, `--speech-threshold`, `--speech-pad-before-ms`, and
  `--speech-pad-after-ms` in `videoflow run`; matching job API, project config,
  MCP overrides, and rack fields.
- `vad_engine` in job results, `run.json`, MCP VAD results, project-state
  config, and JSON Schemas; `doctor` reports the model and ONNX Runtime.
- `scripts/fetch_silero.py` with a pinned URL, SHA-256 verification, and
  `vendor/silero/silero_vad.onnx`; `--with-silero` and `--refresh-silero` in
  the portable build. PyInstaller bundles the model and ONNX Runtime.
- Unit, contract, CLI, project, job, runtime, and portable coverage for Silero,
  engine selection, rescaling, pads, fallback, and packaging.

### Changed

- `work/vad.wav` is written at 16 kHz only when Silero runs; `work/source.wav`
  remains at the source rate and FFmpeg remains the portable fallback.
- Release builds now bundle the Silero model. A build without `--with-silero`
  still runs: `auto` falls back to FFmpeg and `silero` fails with a fetch/build
  hint.
- `videoflow demo` explicitly uses FFmpeg so the self-contained demo does not
  depend on the optional VAD model.

### Verified

- Tests: 284 passed, 12 xfailed, 7 deselected; coverage 99.26%; ruff and mypy
  clean; UI check, Vitest, and production build pass.
- Linux 0.18.0 binary, AppImage, and Windows PE were built and smoke-tested,
  including Silero `vad_engine=silero` runs. The PE was validated under Wine.
- Frozen Linux and Windows project and MCP flows passed with Silero and
  revision snapshots `000001` through `000004`.
- Auto fallback was verified with a missing model; explicit Silero failed with
  `ingest_failed` and the fetch/build hint.

## [0.17.0] — 2026-10-20

### Added

- Persistent projects under `<root>/.videoflow/`: a compact registry, atomic
  state writes, monotonically increasing `revision`, and append-only snapshots
  under `revisions/`.
- Project REST routes: create/list/read, media registration, module config and
  enabled flags, full project run, cancel, SSE events, transcript read and
  sentence overrides, exports, and preset application.
- `ProjectState.revision`, starting at 1 and written into every snapshot.
- Project runs preserve `project_id`, module config, enabled flags, transcript
  word timings, manual overrides, export target flags, and FCPXML dialect.
- Operator presets under `$VIDEOWFLOW_HOME/presets/`, with partial-file
  validation, shipped-name shadowing, list/read/write routes, and atomic apply
  to a project.
- Shared SRT formatting in the domain, used by the REST transcript route and
  MCP resources.

### Changed

- `run_portable` and `JobManager` accept project metadata, revision, config,
  enabled flags, and a preloaded transcript; successful project jobs snapshot
  the state they wrote.
- Per-module reruns return typed `501 not_implemented` until the cache-backed
  module runner lands. The full project run is implemented.
- Project media registration and transcript overrides invalidate stale derived
  results instead of leaving old timeline data looking current.
- API docs now describe the implemented project contract and error statuses.

### Verified

- Tests: 269 passed, 13 xfailed, 7 deselected; coverage 99.26%; ruff and mypy
  clean.
- Project route contracts cover create/list/read, media jail, config validation,
  enabled flags, transcript overrides, exports, presets, project runs, events,
  cancellation, and active-job rejection.
- Linux 0.17.0 binary and AppImage plus Windows PE 0.17.0 build and smoke checks
  are recorded in `releases/v0.17.0/release-notes.md`.

## [0.16.0] — 2026-10-20

### Added

- All twelve MCP tools now execute real work. `run_vad` uses FFmpeg speech
  detection; `transcribe` uses local whisper.cpp and stages an SRT;
  `get_transcript`, culling, zoom, J-cut, shorts, and export tools read and
  modify real project state.
- Staged MCP edits: retake culling, zoom configuration, and J-cuts update
  pending options that the next `videoflow_run_pipeline` applies unless the
  caller explicitly overrides them.
- `videoflow_generate_shorts` returns deterministic vertical clip proposals
  from the cached or project transcript, with retake cuts respected.
- `videoflow_export_fcpxml` exports the latest completed state for Resolve,
  Premiere, or Kdenlive, warns when staged edits are pending, and writes any
  requested output path inside the allowed roots.
- All four MCP resources are live: project state, transcript SRT, presets, and
  export paths. Missing data returns typed errors instead of stubs.
- `videoflow_transcribe` writes its SRT into the target project and stages it,
  so the pipeline uses the exact transcript the agent inspected.

### Changed

- `videoflow_run_vad` takes `noise_db`, `min_silence_ms`, and `min_speech_ms`,
  matching the FFmpeg backend.
- Loading a different source clears the previous MCP job, transcript, pending
  edits, and output context.
- Word-level retake culling returns `word_overrides_not_supported`; sentence
  ids remain the supported granularity.
- MCP documentation and the agent manual now describe the live contract.

### Verified

- Real MCP end-to-end on `jfk.mp4`: load, VAD, local transcription, transcript,
  culling, zoom, J-cut, shorts, pipeline success, all resources, and export.
- Linux 0.16.0 binary and AppImage: `version`, `doctor`, `demo`, and a frozen
  MCP workflow with local whisper.cpp.
- Windows PE 0.16.0 under Wine: `version`, `doctor`, `demo`, and a frozen MCP
  workflow with local `whisper-cli.exe`.
- Tests: 243 passed, 15 xfailed, 7 deselected; coverage 99.22%; ruff and mypy
  clean.

## [0.15.0] — 2026-10-20

### Added

- Offline transcription through the bundled whisper.cpp CLI and a tiny GGML
  model. `--transcribe` with no ASR URL extracts 16 kHz audio and runs locally.
- `whisper_model` in the job API, MCP overrides, and the Transcribe card; an
  empty value uses `ggml-tiny.bin`, a path selects a larger model.
- `scripts/fetch_whisper.py` builds Linux `whisper-cli` from pinned v1.7.6
  source and downloads the official Windows x64 build plus the tiny model.
- `scripts/build_portable.py --with-whisper` bundles the CLI and model.
- Runtime discovery through `VIDEOWFLOW_WHISPER_BIN` and
  `VIDEOWFLOW_WHISPER_MODEL`, with bundled `whisper/` paths as defaults.

### Changed

- ASR URL remains the opt-in remote path; an empty URL now means local
  whisper.cpp instead of a configuration error.
- Portable binaries grow by roughly 80 MB for the CLI and tiny model.

### Verified

- Real Linux `whisper-cli` and Windows `whisper-cli.exe` under Wine transcribe a
  16 kHz WAV to SRT; the adapter parses it into source-sample sentences.

## [0.14.1] — 2026-10-20

### Fixed

- Duration badges show milliseconds under one second instead of `0:00`.
- Header and footer no longer claim Shorts is CLI-only.
- Added a favicon, removing the `/favicon.ico` 404.

### Verified

- Real Chrome session: load, fill paths, enable culling, run, 7 per-block
  progress bars at 100%, global log with 53 lines, keep override, apply, second
  job succeeded. No console errors, request failures, or 4xx/5xx responses.

## [0.14.0] — 2026-10-20

### Added

- Speech-to-text through an OpenAI-compatible `/audio/transcriptions` endpoint,
  with `verbose_json` segments and optional word timings.
- `transcribe`, `asr_base_url`, `asr_model`, and `asr_language` on the job API,
  MCP overrides, and the Transcribe card.
- ASR key stays in `VIDEOWFLOW_ASR_API_KEY`; base URL falls back to
  `VIDEOWFLOW_ASR_BASE_URL`.
- SRT still wins when both a transcript and ASR are configured.
- `transcript_source` in the job report (`srt`, `asr`, or `none`).
- Unit tests for the HTTP client and an end-to-end ASR job.

### Changed

- Version is 0.14.0.
- The Transcribe card is enabled and configurable; local Faster-Whisper is still
  a future adapter.

### Verified

- Fake OpenAI-compatible ASR: 3 segments, `transcript_source=asr`, 3 timeline
  segments, stage `transcribe` succeeded.

## [0.13.0] — 2026-10-20

### Added

- Manual sentence overrides: `POST /api/v1/jobs` accepts `overrides` with
  `sentence_id` and `action` (`keep` or `discard`).
- Overrides are applied after the retake guard, so an editor can keep a culled
  take or discard a kept one. A manual decision wins.
- The inspector lists transcript sentences with Keep/Discard controls and an
  Apply overrides action that starts a new job with the same configuration.
- `manual_override_count` in the job report.
- MCP `overrides` support and unit/API tests.

### Changed

- Version is 0.13.0.

### Verified

- Base cull: 2 segments, 1 cull.
- Keep override: 3 segments, 0 culls, 1 override.
- Discard override: 2 segments, 1 cull, 1 override.

## [0.12.0] — 2026-10-20

### Added

- Shorts run as part of a job: selection, retake-aware conforming, ASS captions,
  1080x1920 MP4 render, a `shorts` stage with progress/logs, and `shorts.json`.
- `POST /api/v1/jobs` accepts `shorts`, `shorts_count`, `shorts_min_sec`,
  `shorts_max_sec`, and `shorts_subtitles`.
- `GET /api/v1/jobs/{id}/shorts/{index}` downloads a rendered vertical clip.
- The Shorts card is configurable and enabled when an SRT is present; the run
  summary lists shorts with download links.
- MCP overrides accept the shorts fields.
- API/journal tests and a real media job with two shorts.

### Changed

- Version is 0.12.0.

### Verified

- Live API job: 7 stages, export + shorts; two 1080x1920 MP4s; short download 200.
- AppImage/Windows PE rebuilt with the Shorts card and telemetry.

## [0.11.0] — 2026-10-20

### Added

- Per-stage telemetry: status, progress, start/finish timestamps, duration, and
  messages for ingest, VAD, SRT import, retakes, J/L cuts, zooms, and export.
- Bounded job logs with module/level filters and a download endpoint. FFmpeg
  commands and the last 50 stderr lines are captured; `job.log` is written to the
  output directory.
- API fields for VAD/pads, J/L offsets, zoom mode/scale/anchor/pan, retake
  strictness/strategy/window, LLM URL/model, and export targets.
- New rack UI: per-block progress, date/duration, status icons, global/per-block
  log drawer, configurable cards, recent jobs, and a run summary.
- Vitest coverage for date/duration/status formatting.
- `GET /api/v1/jobs/{id}/logs` and `?download=1`.

### Changed

- Version is 0.11.0.
- Job timestamps use millisecond precision, so short runs report real durations.

### Verified

- API job reports all stages with durations and logs.
- AppImage and Windows PE rebuilt with the new UI and telemetry.

## [0.10.0] — 2026-10-20

### Added

- Vertical shorts engine: deterministic or LLM sentence selection, retake-aware
  conforming, 1080x1920 H.264/AAC render, and ASS captions.
- `videoflow shorts INPUT --transcript subs.srt -o DIR` with count, duration
  bounds, subtitle toggle, culling, and optional OpenAI-compatible selection.
- `FFmpegAdapter.render_short` with concatenated pieces, center crop, and libass
  burn-in.
- ASS timing/text escaping and source-to-output subtitle mapping.
- Unit and real-media tests for selection, culls, LLM validation, ASS, CLI, and
  vertical output dimensions.

### Changed

- Version is 0.10.0.

### Verified

- Media test renders two 1080x1920 shorts with subtitles from a generated
  fixture.
- Frozen Linux binary and Windows PE (Wine) include the `shorts` command.

## [0.9.1] — 2026-10-20

### Fixed

- AppImage no longer exits immediately when opened without arguments. AppRun now
  starts `serve --open`, keeps the server running, and opens the rack UI.
- `videoflow serve --open` schedules the browser at the correct loopback URL,
  including when bound to `0.0.0.0` or `::`.
- AppImage builds can run `--appdir-only` for contract tests without
  appimagetool.

### Added

- AppDir contract tests for AppRun, desktop entry, icon, and executable bits.
- `scripts/smoke_appimage.py` and a `packaging` pytest marker for a real
  AppImage: version, doctor, demo, extract-and-run fallback, and serve health.

### Changed

- Version is 0.9.1.

## [0.9.0] — 2026-10-20

### Added

- `POST /api/v1/jobs` accepts `transcript` (SRT path) and `cull_retakes`.
  Transcript paths go through the same allowlist as media.
- `GET /api/v1/jobs/{id}/state` returns the project state for the UI inspector.
- The rack UI takes an optional SRT, enables retake culling, and shows culled
  sentences and guard restorations from the job state.
- MCP `videoflow_run_pipeline` overrides accept `transcript`, `cull_retakes`,
  `strictness`, `retake_strategy`, and `context_window`.
- Release artifact names include the version:
  `videoflow-0.9.0-linux-x86_64`, `VideoFlow-0.9.0-x86_64.AppImage`,
  `videoflow-0.9.0-windows-x86_64.exe`.

### Changed

- Version is 0.9.0.
- The job manager builds an LLM client from `VIDEOWFLOW_LLM_BASE_URL`,
  `VIDEOWFLOW_LLM_MODEL`, and `VIDEOWFLOW_LLM_API_KEY` when culling is enabled.

### Verified

- API test for transcript options, path jail, and state output.
- UI `npm run check` and `npm run build` are clean.

## [0.8.0] — 2026-10-20

### Added

- Linux AppImage builder (`scripts/build_appimage.py`) wrapping the onefile
  binary, with an icon, desktop entry, and AppRun.
- Portable Linux data directory next to the AppImage (`APPIMAGE` aware).
- Windows PE build path without GitHub Actions: Wine WoW64 + Windows embeddable
  Python + PyInstaller, with Windows FFmpeg binaries.
- `release.py` stages multiple artifacts, checksums, and a manifest.
- Releases now include Linux binary, AppImage, and Windows `.exe`.

### Changed

- Version is 0.8.0.
- GitHub Actions workflows removed. Builds and smoke tests are local.
- `packaging/videoflow.spec` accepts `VIDEOWFLOW_VENDOR_DIR` for cross-OS
  binaries.

### Verified

- AppImage: `doctor` and `demo`, three exports, bundled FFmpeg.
- Windows PE under Wine: `version`, `doctor`, `demo`, three exports, bundled
  FFmpeg.
- Both artifacts are staged in `releases/v0.8.0/`.

## [0.7.0] — 2026-10-19

### Added

- `GET /api/v1/jobs/{id}/artifacts/{target}` serves a generated timeline for
  download, confined to the job output directory.
- UI artifact cards are download links.
- Quick presets in the portable panel: YouTube, Lecture, Shorts.

### Changed

- Version is 0.7.0.

### Verified

- API contract test for in-output downloads and unknown artifacts.
- `npm run check` and `npm run build` are clean.

## [0.6.0] — 2026-10-19

### Added

- SRT transcript import with exact sample-time conversion.
- OpenAI-compatible JSON client: Ollama, LM Studio, Groq, and other
  `/chat/completions` endpoints; temperature 0; response-format fallback; no key
  in errors.
- Transcript-driven retake culling with overlapping context windows, strict id
  validation, exact-repeat fallback, and the `keep_last`/`keep_best` guard.
- `videoflow run --transcript subs.srt --cull-retakes`, optional LLM via
  `--llm-base-url`, and strictness/strategy/window flags.
- Transcript and retake decisions are persisted in `project_state.json` and
  reported in `run.json`.
- `--min-speech-ms` removes sub-100 ms blips left by codec edges.
- Tests for SRT parsing, LLM transport, chunking, guard restoration, interval
  subtraction, and the culling pipeline.

### Changed

- Version is 0.6.0.
- The LLM adapter is now a real implementation; its contract xfail is removed.

### Verified

- Frozen Linux binary: `--transcript` + `--cull-retakes` culls an exact repeat.
- Frozen Linux binary against a local OpenAI-compatible server: the model
  discards both attempts, the guard restores the last one, and the run reports
  one cull plus one restoration.

## [0.5.0] — 2026-10-19

### Added

- The SvelteKit rack starts real portable jobs: source/output fields, silence
  and zoom options, live progress, cancel, artifact paths, and typed errors.
- Module cards reflect live job stages. Neural modules are marked `later` and
  render as bypassed.
- Typed API client (`ui/src/lib/api.ts`) for system info and jobs.
- `releases/` policy, a `scripts/release.py` staging tool, checksums, manifests,
  and notes per version.
- Tag builds attach Linux and Windows binaries to the GitHub Release.

### Changed

- Version is 0.5.0.
- The served UI is no longer a static-only shell; it drives the portable API.

### Verified

- `npm run check` and `npm run build` are clean.
- The frozen binary serves the new UI, and the browser page is produced from the
  bundle.

## [0.4.0] — 2026-10-19

### Added

- `JobManager`: in-process jobs with queued/running/succeeded/failed/cancelled
  states, progress, cancellation between stages, bounded concurrency, and history
  pruning.
- REST routes: `POST /api/v1/jobs`, list, get, cancel, per-job SSE, and
  `/api/v1/system`.
- Path allowlist on HTTP and MCP inputs through `VIDEOWFLOW_ALLOWED_ROOTS`,
  defaulting to home, cwd, and the portable data directory.
- Live MCP tools: `videoflow_load_media`, `videoflow_run_pipeline`,
  `videoflow_get_job`, and `videoflow_cancel_job` now call the real pipeline.
  `run_pipeline` accepts optional `source` and `output`.
- Pipeline progress stages: probe, extract, VAD, timeline, export, state.
- Job and API contract tests, plus a real-media API job test.

### Changed

- Version is 0.4.0.
- `create_app` owns the API routes; `create_http_app` adds MCP and the static UI.
- `videoflow serve` now exposes a working job API, not only health.

### Verified

- Frozen Linux binary: POST job → poll → succeeded with three artifacts; SSE
  returns the terminal state; MCP stdio `load_media → run_pipeline → get_job`
  produces three artifacts.

## [0.3.0] — 2026-10-19

### Added

- Unified `videoflow` CLI: `run`, `serve`, `mcp`, `doctor`, `demo`, `version`.
- Model-free speech detection with FFmpeg `silencedetect`, including a parser and
  complement calculation.
- Portable pipeline service: probe, PCM, speech detection, timeline, three
  exports, `project_state.json`, and `run.json`.
- Portable runtime: data directory next to the executable, `VIDEOWFLOW_HOME`,
  binary discovery from the bundle, sibling files, then `PATH`.
- PyInstaller onefile spec, build script with FFmpeg bundling, and a Linux/Windows
  CI matrix with smoke tests.
- Static rack UI served by `videoflow serve` when the UI was built.
- MCP no-trailing-slash redirect (`/mcp` → `/mcp/`).

### Changed

- Version is 0.3.0.
- The API app can mount the built UI at `/`.
- Documentation adds a portable manual and ADR-0010.

### Verified

- Linux onefile (168 MB with static FFmpeg) runs with `PATH` empty: bundled
  FFmpeg and FFprobe are found, `doctor` passes, `demo` produces three artifacts,
  `serve` answers `/health`, `/`, and `/mcp/`, and MCP stdio lists twelve tools.
- Windows is built and smoke-tested in the CI matrix; no Windows binary was
  produced in this Linux workspace.

## [0.2.0] — 2026-10-19

### Added

- FFprobe ingest with rational frame rate, frame count, dimensions, and audio
  sample rate. Missing or unreadable sources fail with `ingest_failed`.
- PCM extraction to 16 kHz mono WAV with atomic replacement and SHA-256 digest.
- Deterministic timeline builder: span normalisation, frame coverage,
  sample-aligned audio, J/L-cut boundary shifts with handle checks, fade metadata,
  and alternating punch-in/pan transforms.
- FCPXML 1.9/1.10 writer with `audioStart`/`audioDuration` for J/L-cuts and
  `adjust-transform` for zoom.
- xmeml (FCP 7 XML) writer with separate video and audio tracks and a Basic
  Motion filter.
- OTIO writer with V1/A1 tracks for Kdenlive 25.04+.
- `export_timeline` service that writes all three artifacts from one validated
  timeline.
- Real-FFmpeg media tests for generated fixtures.
- Timeline builder and exporter contract tests.

### Changed

- Version is 0.2.0.
- Coverage gate now includes the deterministic timeline builder.
- Media, slow, and manual tests are excluded from the default pytest run. Run
  them with `-m media --no-cov`.

### Known gaps

- Audio transitions are not emitted in the NLE artifacts yet; the fade samples are
  recorded in state and the AC-01 contract remains xfail.
- Progressive zoom is stored as metadata but not emitted as keyframes.
- Neural engines, jobs, project routes, SSE, live MCP results, MP4 render, and the
  interactive rack are still stubs.

## [0.1.0] — 2026-10-19

### Added

- English normative product requirements, architecture, data model, timebase,
  pipeline, cache, security, and test plan.
- Specifications for all eight rack modules, the REST API, the MCP server, the
  rack UI, and the three NLE exporters.
- Nine ADRs covering rational time, hexagonal boundaries, secrets, NLE dialects,
  MCP transports, XML building, the retake guard, CPU-first defaults, and the
  single-user runtime.
- User, operator, developer, MCP agent, NLE import, and testing manuals.
- Pydantic project state, module configs, presets, job and error models.
- Committed JSON Schemas generated from the models.
- Rational `Timebase` with frame coverage, pads, and exact round-trips.
- Cache canonicalization and module hashing without mtime.
- Run planning with upstream-dirty rules and bypass handling.
- Retake keeper guard, exact repetition clustering, and restoration records.
- Path allowlist jail, secret redaction, and timeline overlap checks.
- FastAPI health endpoint and MCP Streamable HTTP mount.
- MCP SDK server with twelve tools and four resources, returning structured
  `not_implemented` results.
- Three shipped presets: `youtube-talking-head`, `shorts-aggressive`,
  `lecture-clean`.
- 107 passing unit/contract tests, 21 strict xfails for unbuilt engines, and
  99% coverage on the pure core.
- SvelteKit and Tailwind rack scaffold with the eight module cards.
- CI workflow for tests, coverage, lint, and types.

### Changed

- The Portuguese brief moved to `docs/origin/prd-pt.md` and is non-normative. The
  old `requirements.txt` name was removed because Python treats it as a
  dependency list.
- FCPXML is no longer claimed as a Premiere import format. Premiere receives
  xmeml; Kdenlive receives OTIO.
- Neural defaults are CPU/int8/small, not CUDA/float16/large-v3.
- Authoritative time is rational frames and samples, not float seconds.

### Known gaps

- Media engines, exporters, job execution, project routes, SSE, and the live rack
  are specified and stubbed.
- No license has been chosen.
- No face tracking in v1.
- The NLE compatibility spike and long-file manual QA are not yet executed.

### Security

- Secrets are names in state and values only in the environment or a mode-0600
  file.
- The API binds to loopback and CORS is limited to the local UI.
