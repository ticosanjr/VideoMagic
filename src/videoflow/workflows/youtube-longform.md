---
schema_version: 1
version: 1
workflow_id: youtube-longform
name: YouTube Longform 16:9
description: Edição completa de vídeo longo com B-roll, motion, QA e entrega multi-NLE.
aspect_ratio: "16:9"
platforms: ['youtube']
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
  - id: cull
    node: session.cull
    purpose: session.cull
    requires_approval: false
  - id: gaze
    node: vision.gaze
    purpose: vision.gaze
    requires_approval: false
  - id: pacing
    node: pacing.visual_audit
    purpose: pacing.visual_audit
    requires_approval: false
  - id: beatmap
    node: timeline.apply_beatmap
    purpose: timeline.apply_beatmap
    requires_approval: true
  - id: assets
    node: assets.plan
    purpose: assets.plan
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

# YouTube Longform 16:9

## Objetivo

Edição completa de vídeo longo com B-roll, motion, QA e entrega multi-NLE.

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
- id: transcribe
  node: transcribe
  purpose: transcribe
  requires_approval: false
- id: cull
  node: session.cull
  purpose: session.cull
  requires_approval: false
- id: gaze
  node: vision.gaze
  purpose: vision.gaze
  requires_approval: false
- id: pacing
  node: pacing.visual_audit
  purpose: pacing.visual_audit
  requires_approval: false
- id: beatmap
  node: timeline.apply_beatmap
  purpose: timeline.apply_beatmap
  requires_approval: true
- id: assets
  node: assets.plan
  purpose: assets.plan
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

