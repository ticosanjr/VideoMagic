---
schema_version: 1
version: 2
workflow_id: reels-from-raw
name: "Reels / Short Direto do Bruto (9:16)"
description: "Transforma gravação bruta curta em Reel/Short pronto com decupagem inteligente, B-roll suave e legenda queimada."
aspect_ratio: "9:16"
platforms:
  - reels
  - tiktok
  - shorts
inputs:
  - source
steps:
  - id: ingest
    node: ingest
    purpose: "Ingestão CFR e WAV 48 kHz"
    requires_approval: false
  - id: decupage
    node: decupage.snap
    purpose: "Decupagem agressiva + revisão de retakes pelo OpenCode"
    requires_approval: false
  - id: scenes
    node: scene.analyze
    purpose: "Detecção facial e proteção de tela"
    requires_approval: false
  - id: render
    node: shorts.render
    purpose: "Render vertical com legendas queimadas e áudio -16 LUFS"
    requires_approval: false
  - id: qa
    node: qa.final
    purpose: "QA de safe-zone e loudness"
    requires_approval: false
approvals:
  - curation
default_style: "canal-paula-reels"
compatible_styles:
  - canal-paula-reels
  - sr-viral-depth-split
  - sr-feed-4x5-card
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
updated_at: "2026-11-25T12:00:00Z"
---

# Reels Direto do Bruto

## Sequência Obrigatória MCP

1. `vf_project(action="init")` → `vf_ingest` → `vf_style(action="apply")`.
2. `vf_decupage(action="review_packet")` → OpenCode remove retakes com `discard_sentences` → `vf_decupage(action="run_full", pacing_profile="tight", wait=True)`.
3. `vf_scenes` → `vf_transcript(action="editorial_map")`.
4. Se houver B-roll/imagens: `vf_media` + `image_to_broll_motion` (`1.00→1.06`) + `vf_curation` (se modo curadoria).
5. `vf_shorts(action="batch", burn_subtitles=True, wait=True)` + `vf_export(targets=["resolve", "premiere", "kdenlive"])`.
