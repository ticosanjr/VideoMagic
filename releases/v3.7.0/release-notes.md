# VideoFlow 3.7.0

VideoFlow 3.7.0 adds the decupage acoustic phase, Scene Intelligence, and the
Dynamic Shorts compositor, while keeping all heavy work optional on the LAN
worker.

## Highlights

- Decupage: `audio.events`, VAD hysteresis + RMS, anti-hallucination ASR,
  forced alignment, ASUs, prefilter, explicit LLM caller/videoflow/none,
  snap, timeline, quarantine, and benchmark.
- Scene Intelligence: PySceneDetect cuts fused with decupage jumps, MediaPipe/
  Haar face metrics, Canny/Laplacian layouts, editing hints, 544 px keyframes,
  SHA-256 cache, `scenes_manifest.json`, and `timeline_supercontext.json`.
- Dynamic Shorts: `short.plan`, `short.captions`, `short.validate`,
  `short.render`, `short.export`, and `short.qa`.
- Layouts: `FULL_FACE`, `SPLIT_BROLL`, `SPLIT_SCREEN_SAFE`,
  `SPLIT_SCREEN_FILL`; dual-canvas and dual-file topologies.
- Captions: 3–4 word ASS blocks, per-layout Y, overlap sanitizer, layout snapping,
  SFX cues, 350 ms end padding, 80 ms fade.
- Render: per-segment filter scripts, concat, ASS burn, loudnorm, NVENC on the
  worker, local libx264 fallback with explicit degradation.
- FCPXML: V1 base, V2 face panels, A1 voice, A2 SFX, editable captions, markers,
  offline-media validation.
- MCP: `vf_scenes` plus 34 core tools and 16 resources.
- Delivery: optional `delivery.collect`; custom output paths remain valid.

## Artifacts

- `VideoFlow-3.7.0-linux-x86_64.tar.zst` — portable Linux bundle.
- `sbom.json`.
- `SHA256SUMS` and `manifest.json`.

Windows GPU worker wheel: `videoflow_gpu_worker-3.7.0-py3-none-any.whl` is in
`src/videoflow/templates/wheels/`.

## Verification

- MCP gate: 411 passed, 85% MCP coverage, 34 tools, 16 resources.
- Python non-media: 2,817 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- Shorts benchmark: synthetic 10-minute corpus, F1 1.0, scene detection
  34.2 s/h (target 45); full enrichment 75 s/h reported separately.

## Known limitations

- Physical Windows RTX 3060 NVENC certification is still pending; no GPU speedup
  is claimed from local CI.
- The scene benchmark corpus is synthetic; replace it with annotated production
  footage before claiming production F1.
- Resolve import remains a manual smoke; `scripts/fcpxml_smoke.py` validates
  structure and media first.
- `dual_file` Shorts require an explicit screen video path.
