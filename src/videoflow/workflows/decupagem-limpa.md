---
schema_version: 1
version: 1
workflow_id: decupagem-limpa
name: Decupagem Limpa
description: Ingestão multi-take/multicam, sincronia, corte de retakes e export NLE.
aspect_ratio: "16:9"
platforms: ['youtube', 'resolve', 'premiere', 'kdenlive']
inputs:
  - source
steps:
  - id: ingest
    node: ingest
    purpose: ingest
    requires_approval: false
  - id: vad
    node: audio.vad
    purpose: audio.vad
    requires_approval: false
  - id: transcribe
    node: transcribe
    purpose: transcribe
    requires_approval: false
  - id: cull
    node: session.cull
    purpose: session.cull
    requires_approval: false
  - id: sync
    node: sync.multicam_audio
    purpose: sync.multicam_audio
    requires_approval: false
  - id: timeline
    node: edit.timeline
    purpose: edit.timeline
    requires_approval: false
  - id: export
    node: export.nle
    purpose: export.nle
    requires_approval: true
approvals:
  - beatmap
  - final_export
default_style: ""
compatible_styles: []
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
updated_at: "2026-11-18T00:00:00Z"
---

# Decupagem Limpa

## Objetivo

Ingestão multi-take/multicam, sincronia, corte de retakes e export NLE.

## Regras

1. Ler `AGENTS.md`, `presets/*.md` e este workflow.
2. Perguntar ao usuário qual Estilo aplicar.
3. Gerar `beat_map.json` e aguardar aprovação antes de montar.
4. Usar somente ferramentas atômicas.
5. Rodar `qa.visual_10fps` antes da entrega.
6. Exportar `mp4_youtube`, `resolve`, `premiere` e `kdenlive`.

## Etapas

- id: ingest
  node: ingest
  purpose: ingest
  requires_approval: false
- id: vad
  node: audio.vad
  purpose: audio.vad
  requires_approval: false
- id: transcribe
  node: transcribe
  purpose: transcribe
  requires_approval: false
- id: cull
  node: session.cull
  purpose: session.cull
  requires_approval: false
- id: sync
  node: sync.multicam_audio
  purpose: sync.multicam_audio
  requires_approval: false
- id: timeline
  node: edit.timeline
  purpose: edit.timeline
  requires_approval: false
- id: export
  node: export.nle
  purpose: export.nle
  requires_approval: true

