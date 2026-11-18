---
schema_version: 1
version: 1
workflow_id: clone-style
name: Clone Style
description: Engenharia reversa de estilo a partir de URL ou references/ e salvamento no catálogo.
aspect_ratio: "auto"
platforms: ['youtube', 'reels', 'shorts']
inputs:
  - source
steps:
  - id: capture
    node: capture_web_or_screen
    purpose: capture_web_or_screen
    requires_approval: false
  - id: analyze
    node: analyze_reference_style
    purpose: analyze_reference_style
    requires_approval: false
  - id: save
    node: style.save
    purpose: style.save
    requires_approval: false
  - id: sync
    node: style.sync
    purpose: style.sync
    requires_approval: false
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

# Clone Style

## Objetivo

Engenharia reversa de estilo a partir de URL ou references/ e salvamento no catálogo.

## Regras

1. Ler `AGENTS.md`, `presets/*.md` e este workflow.
2. Perguntar ao usuário qual Estilo aplicar.
3. Gerar `beat_map.json` e aguardar aprovação antes de montar.
4. Usar somente ferramentas atômicas.
5. Rodar `qa.visual_10fps` antes da entrega.
6. Exportar `mp4_youtube`, `resolve`, `premiere` e `kdenlive`.

## Etapas

- id: capture
  node: capture_web_or_screen
  purpose: capture_web_or_screen
  requires_approval: false
- id: analyze
  node: analyze_reference_style
  purpose: analyze_reference_style
  requires_approval: false
- id: save
  node: style.save
  purpose: style.save
  requires_approval: false
- id: sync
  node: style.sync
  purpose: style.sync
  requires_approval: false

