---
schema_version: 1
version: 2
workflow_id: clone-style
name: "Clonar Estilo de Referência"
description: "Extrai paleta, ritmo, tipografia e regras de uma URL ou imagem/vídeo em references/ e salva no catálogo."
aspect_ratio: "auto"
platforms:
  - youtube
  - reels
  - shorts
inputs:
  - source
steps:
  - id: clone
    node: style.reverse_engineer
    purpose: "Extrair paleta, fontes e ritmo da referência"
    requires_approval: false
approvals:
  - style_save
default_style: ""
compatible_styles: []
export_targets: []
updated_at: "2026-11-25T12:00:00Z"
---

# Clonar Estilo de Referência

## Sequência Obrigatória MCP

1. Se o usuário fornecer URL, capturar via `vf_fx_capture`; se fornecer arquivos em `references/`, ler os caminhos.
2. Executar `vf_style(action="clone_from_reference")` → `vf_style(action="validate")` → `vf_style(action="save")`.
3. Gerar `vf_style(action="preview", duration_sec=5.0)` para validação visual rápida.
