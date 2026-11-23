---
schema_version: 1
version: 1
workflow_id: reels-from-raw
name: Reels from Raw 9:16
description: Transforma gravação bruta em Reel vertical com corte agressivo, cutout e legendas cinéticas.
aspect_ratio: "9:16"
platforms: ['reels', 'tiktok', 'shorts']
inputs:
  - source
steps:
  - id: ingest
    node: ingest
    purpose: ingest
    requires_approval: false
  - id: transcribe
    node: transcribe
    purpose: transcribe
    requires_approval: false
  - id: editorial
    node: speech.editorial_clean
    purpose: speech.editorial_clean
    requires_approval: false
  - id: cull
    node: retakes.cull
    purpose: retakes.cull
    requires_approval: false
  - id: select
    node: shorts.select
    purpose: shorts.select
    requires_approval: false
  - id: reframe
    node: shorts.reframe
    purpose: shorts.reframe
    requires_approval: false
  - id: curation
    node: curation.prepare
    purpose: curation.prepare
    requires_approval: true
  - id: captions
    node: shorts.captions
    purpose: shorts.captions
    requires_approval: false
  - id: motion
    node: motion.render
    purpose: motion.render
    requires_approval: false
  - id: qa
    node: qa.visual_10fps
    purpose: qa.visual_10fps
    requires_approval: false
  - id: export
    node: export.nle
    purpose: export.nle
    requires_approval: true
approvals:
  - beatmap
  - curation
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

# Reels from Raw 9:16

## Objetivo

Transforma gravação bruta em Reel vertical com corte agressivo, cutout e legendas cinéticas.

## Regras

1. Ler `AGENTS.md`, `presets/*.md` e este workflow.
2. Perguntar Estilo, Workflow e Modo (`curation` ou `autonomous`).
3. Gerar `beat_map.json` e aguardar aprovação antes de montar.
4. No modo curadoria, publicar `vf_curation` e aguardar a escolha humana;
   no modo autônomo, usar `auto_select`.
5. Usar somente ferramentas atômicas.
6. Rodar `qa.visual_10fps` antes da entrega.
7. Exportar `mp4_youtube`, `resolve`, `premiere` e `kdenlive`.

## Etapas

- id: ingest
  node: ingest
  purpose: ingest
  requires_approval: false
- id: transcribe
  node: transcribe
  purpose: transcribe
  requires_approval: false
- id: editorial
  node: speech.editorial_clean
  purpose: speech.editorial_clean
  requires_approval: false
- id: cull
  node: retakes.cull
  purpose: retakes.cull
  requires_approval: false
- id: select
  node: shorts.select
  purpose: shorts.select
  requires_approval: false
- id: reframe
  node: shorts.reframe
  purpose: shorts.reframe
  requires_approval: false
- id: curation
  node: curation.prepare
  purpose: curation.prepare
  requires_approval: true
- id: captions
  node: shorts.captions
  purpose: shorts.captions
  requires_approval: false
- id: motion
  node: motion.render
  purpose: motion.render
  requires_approval: false
- id: qa
  node: qa.visual_10fps
  purpose: qa.visual_10fps
  requires_approval: false
- id: export
  node: export.nle
  purpose: export.nle
  requires_approval: true

