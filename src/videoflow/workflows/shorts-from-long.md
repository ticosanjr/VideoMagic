---
schema_version: 1
version: 1
workflow_id: shorts-from-long
name: Shorts from Long
description: Deriva vários Shorts/Reels de um vídeo longo já decupado.
aspect_ratio: "9:16"
platforms: ['shorts', 'reels', 'tiktok']
inputs:
  - source
steps:
  - id: load
    node: timeline.load
    purpose: timeline.load
    requires_approval: false
  - id: beats
    node: narrative.beats
    purpose: narrative.beats
    requires_approval: false
  - id: select
    node: shorts.select
    purpose: shorts.select
    requires_approval: false
  - id: score
    node: shorts.score
    purpose: shorts.score
    requires_approval: false
  - id: reframe
    node: shorts.reframe
    purpose: shorts.reframe
    requires_approval: false
  - id: captions
    node: shorts.captions
    purpose: shorts.captions
    requires_approval: false
  - id: render
    node: shorts.render
    purpose: shorts.render
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

# Shorts from Long

## Objetivo

Deriva vários Shorts/Reels de um vídeo longo já decupado.

## Regras

1. Ler `AGENTS.md`, `presets/*.md` e este workflow.
2. Perguntar ao usuário qual Estilo aplicar.
3. Gerar `beat_map.json` e aguardar aprovação antes de montar.
4. Usar somente ferramentas atômicas.
5. Rodar `qa.visual_10fps` antes da entrega.
6. Exportar `mp4_youtube`, `resolve`, `premiere` e `kdenlive`.

## Etapas

- id: load
  node: timeline.load
  purpose: timeline.load
  requires_approval: false
- id: beats
  node: narrative.beats
  purpose: narrative.beats
  requires_approval: false
- id: select
  node: shorts.select
  purpose: shorts.select
  requires_approval: false
- id: score
  node: shorts.score
  purpose: shorts.score
  requires_approval: false
- id: reframe
  node: shorts.reframe
  purpose: shorts.reframe
  requires_approval: false
- id: captions
  node: shorts.captions
  purpose: shorts.captions
  requires_approval: false
- id: render
  node: shorts.render
  purpose: shorts.render
  requires_approval: false
- id: export
  node: export.nle
  purpose: export.nle
  requires_approval: true

