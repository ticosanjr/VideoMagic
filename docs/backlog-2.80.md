# VideoFlow 2.80 — Headless MCP backlog

This is the execution backlog for the 2.80 Headless MCP Edition. It is ordered
by dependency; a phase only closes when its acceptance checks are green.

Status legend: `[ ]` pending, `[-]` in progress, `[x]` done.

## Phase 0 — foundation

- [x] Domain models for beat maps, archetypes, QA, safe zones, pacing, gaze,
      captures, reference boards, transformative records, SFX, presets, NLE
      sync, intros, sync diagnostics, and self-heal reports.
- [x] Settings sections: `headless`, `sync`, `render`, `qa`, `web_render`,
      `presets`; backward-compatible defaults.
- [x] Feature flags and step statuses; old recipes and 74 MCP tools unchanged.
- [x] Documentation skeleton for 2.80.

## Phase 1 — core P0

- [x] `videoflow serve --mcp-only` / `--no-ui`: no Svelte mount, no tray, no
      PyGObject, no UI browser/polling.
- [x] `create_app`/`create_http_app` headless parameters and startup logging.
- [x] VFR detection and CFR normalisation in ingest.
- [x] Optional ingest proxy.
- [x] `speech.offset_mode`, `speech.offset_ms`, `sync.drift_threshold_ms`.
- [x] Offset/onset diagnostic and optional external-mic drift measurement.
- [x] `application/render_gate.py` with process-wide and cross-process
      serialisation, status metrics.
- [ ] Draft render flags (`draft_scale`, `motion_blur`) in renderers.
- [x] `step.self_heal` with structured repair reports.
- [x] Optional-model catalog entries and update API.

## Phase 2 — new DAG steps

- [x] `motion.web_render`
- [x] `layout.cutout`
- [x] `qa.visual_10fps`
- [x] `qa.safezone`
- [x] `pacing.visual_audit`
- [x] `vision.gaze`
- [x] `assets.screen_capture`
- [x] `assets.reference_board`
- [x] `assets.transformative_guard`
- [x] `sfx.procedural`
- [x] `style.reverse_engineer`
- [x] `preset.compile_rule`
- [x] `nle.sync_back`
- [x] `intro.assemble_last`

Each step needs params, ports, manifest metadata, cache rules, fallback, unit
tests, and a media/contract test where applicable.

## Phase 3 — MCP surface

- [x] `vf_beatmap_execute`
- [x] `vf_preview_archetypes`
- [x] `vf_web_scene_preview`
- [x] `vf_audio_patch_line`
- [x] `vf_nle_roundtrip`
- [x] `vf_qa_inspect_window`
- [x] `vf_preset_rules`
- [x] `vf_style_clone`
- [x] Resources: `vf://project/{id}/beat_map`,
      `vf://project/{id}/qa_report`, `vf://presets/{channel_id}/rulebook`,
      `vf://specs/safezones`.
- [x] Tool/resource count contract: 82 tools, 9 resources.

## Phase 4 — headless recipes

- [x] `opencode_longform_studio`
- [x] `opencode_reels_from_raw`
- [x] `opencode_shorts_batch_from_long`
- [x] `opencode_clone_style`

## Phase 5 — flexibilisations

- [x] `retakes.cull` / `audio.vad`: per-call silence and aggressiveness.
- [x] `shorts.select` / `shorts.score`: hook criteria, rewrite, layout.
- [x] `broll.generate`: reference frame.
- [x] `audio.master` / `music.beat`: platform LUFS and three-act music.
- [x] `export.nle`: adjustment layers, LUT, grain.

## Phase 6 — interface and docs

- [x] MCP hybrid usage note in the Connect/Integrations interface.
- [x] `docs/mcp.md` headless setup, OpenCode examples, tool/resource catalog.
- [x] Settings docs, recipes docs, OpusClip parity update, 3.0 blockers.
- [x] Optional-model management docs.

## Phase 7 — verification and release

- [ ] Raise full-tree coverage back to ≥95% for the new partial/optional
  bridges, or explicitly exclude platform-only code with justification.

- [ ] Unit, contract, media, MCP protocol, headless import, performance and
      security tests.
- [ ] Fast gate and full gate.
- [x] 2.80.0 version bump, CHANGELOG, release notes.
- [x] Fast onedir/tar release and full onefile/AppImage release.
- [x] SHA256SUMS, SBOM, AppImage/tray smoke.


## Current status (2.80.0 work tree)

Implemented in this pass:

- Headless API/MCP mode, CFR/proxy ingest, offset/drift reporting, render gate,
  structured self-heal.
- All 14 new step types registered; deterministic implementations are live for
  safe zones, pacing, procedural SFX, rulebooks, reference boards, gaze fallback,
  style presets, intro plans, transformative plans, NLE reports, cutout plans,
  and the web-render bridge.
- Eight `vf_*` tools and four `vf://` resources; 82 tools and 9 resources.
- Four OpenCode recipes validate end-to-end.
- Optional model catalog entries and update API/UI button.

Still required after 2.80.0:

- Wire draft scale/motion blur through every renderer.
- Replace plan-only paths for cutout, web render, screen capture clips, and NLE
  apply with rendered output. Audio line patch now synthesizes and crossfades.
- Complete flexibilisations (`retakes.cull`, `audio.vad`, shorts hooks, B-roll
  reference frame, platform LUFS, NLE adjustment layers).
- Media/performance/security evidence and full gate.
- Version bump, release notes, AppImage/tar staging.
