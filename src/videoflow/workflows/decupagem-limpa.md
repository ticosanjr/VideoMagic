---
schema_version: 1
version: 2
workflow_id: decupagem-limpa
name: "Decupagem Limpa + NLE com Quarentena"
description: "Corte ultra-preciso de silêncios, gagueiras e retakes (com revisão semântica do OpenCode) entregando MP4 + FCPXML com trilha Quarantine V2/A2."
aspect_ratio: "16:9"
platforms:
  - youtube
  - resolve
  - premiere
  - kdenlive
inputs:
  - source
steps:
  - id: ingest
    node: ingest
    purpose: "Ingestão CFR e WAV 48 kHz"
    requires_approval: false
  - id: decupage
    node: decupage.snap
    purpose: "VAD + ASR + revisão semântica + snap com piso fonético"
    requires_approval: false
  - id: audio
    node: audio.finalize
    purpose: "Diálogo normalizado -16 LUFS / 48 kHz"
    requires_approval: false
  - id: export
    node: export.nle
    purpose: "MP4 + FCPXML (trilha Quarantine V2/A2) + Premiere + Kdenlive"
    requires_approval: false
approvals:
  - final_export
default_style: "canal-paula-long"
compatible_styles:
  - canal-paula-long
  - canal-rafael-tech
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
updated_at: "2026-11-25T12:00:00Z"
---

# Decupagem Limpa

## Sequência Obrigatória MCP

1. `vf_project(action="init")` → `vf_ingest`.
2. `vf_decupage(action="review_packet")`: o OpenCode analisa **todas** as sentenças, marca retakes/frases repetidas (inclusive distantes) via `vf_decupage(action="discard_sentences")` e executa `vf_decupage(action="run_full", pacing_profile="tight", wait=True)`.
3. `vf_audio(action="master")` → `vf_export(action="bundle", targets=["mp4", "resolve", "premiere", "kdenlive"], mode="preview" ou "final")`.
