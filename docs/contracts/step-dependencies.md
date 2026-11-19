# Step dependencies

The planner must inject missing prerequisites or fail in preflight. It must not
fail in the middle of a long render.

## Canonical chain

1. `ingest`
2. `audio.vad` (requires `ingest`)
3. `audio.events` (requires `ingest`, optional)
4. `transcribe` (requires `ingest`)
5. `alignment.forced` (requires `transcribe`, optional)
6. `speech.asu` (requires `transcribe` and `audio.vad`)
7. `decupage.prefilter` (requires `speech.asu`)
8. `decupage.llm` (requires `speech.asu`; may pause for caller input)
9. `decupage.apply` (requires `speech.asu` and validated decisions)
10. `decupage.snap` (requires `speech.asu` plus optional decisions)
11. `decupage.timeline` (requires `decupage.snap`)
12. `edit.timeline` (requires `audio.vad`)
8. `audio.finalize` (requires `edit.timeline`, optional music/Foley)
9. `vf_export` (requires `audio.finalize`)
10. `vf_qa_final` (requires the exported artifact)
11. `delivery.collect` is optional after the final export; it consolidates
    `VideoFlow_Output/` but is never required for validation.
12. `scene.analyze` (after `ingest`; optionally after `decupage.snap` to fuse
    visual cuts with decupage jumps)
13. `short.plan` (after `scene.analyze`; resolves scene anchors into a
    contiguous 1080x1920 composition plan)
14. `short.captions` (after `short.plan`; snaps layout cuts to caption/ASU
    boundaries, writes ASS, SFX cues, and end padding)
15. `short.validate` (after `short.captions`; re-checks coverage, B-roll,
    upscale, crops, captions, and safe zones before render)
16. `short.render` (after `short.captions`; runs local/remote micro-clips,
    concat, ASS burn, and loudness normalization)
17. `short.export` (after `short.render`; writes FCPXML V1/V2/A1/A2 plus face
    panel clips)
18. `short.qa` (after `short.export`; validates render, captions, safe zones,
    duration, and FCPXML tracks)

## Rules

- `audio.mix`/`audio.master` are legacy and must not run after
  `audio.finalize`.
- `vf_export` never starts if the timeline is missing.
- `vf_qa_final` never mutates the timeline.
- `vf_shorts_batch` requires a transcript and a non-empty clips list.
- `vf_depth_composite` requires a timeline and a source.
- `speech.asu` must run after alignment when alignment is enabled; it never
  changes the transcript or the timeline.
- `decupage.llm` must never call a model when `llm_policy="caller"`; it writes
  the request and waits for `decupage.apply`.
- `decupage.apply` is the only step that turns LLM decisions into cuts.
- Remote ASR/alignment failures fall back locally unless the step uses
  `compute_policy="remote_only"`.
