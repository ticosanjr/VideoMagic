---
schema_version: 1
version: 2
workflow_id: shorts-from-long
name: "Shorts & Reels de Vídeo Longo (9:16 / 4:5)"
description: "Extrai os melhores ganchos da timeline já decupada usando análise de cena + fala, com legendas queimadas e curadoria."
aspect_ratio: "9:16"
platforms:
  - shorts
  - reels
  - tiktok
inputs:
  - source
steps:
  - id: scenes
    node: scene.analyze
    purpose: "Identificar cenas em câmera vs tela compartilhada"
    requires_approval: false
  - id: select
    node: shorts.select
    purpose: "Selecionar ganchos completos (25–45 s) na Edited Timeline"
    requires_approval: false
  - id: curation
    node: curation.prepare
    purpose: "Aprovação opcional dos trechos e B-rolls na UI"
    requires_approval: true
  - id: render
    node: shorts.render
    purpose: "Reframe facial + multi-layout + legendas queimadas + -16 LUFS"
    requires_approval: false
  - id: qa
    node: qa.final
    purpose: "Auditoria de safe-zone, duração e loudness por Short"
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
updated_at: "2026-11-25T12:00:00Z"
---

# Shorts & Reels de Vídeo Longo

## Sequência Obrigatória MCP

1. Ler `vf_transcript(action="editorial_map")` na timeline já decupada.
2. Escolher 2 a 5 janelas de `25–45 s` com gancho + conclusão completa em cenas `TALKING_HEAD` (evitar crop central 9:16 sobre `SCREEN_SHARE_FULL`; usar `SPLIT_SCREEN_SAFE` se incluir tela).
3. Se o estilo pedir abertura 3D (`sr-viral-depth-split`), aplicar `vf_fx_depth` apenas em `0–3 s`.
4. Chamar `vf_shorts(action="batch", time_basis="edited", burn_subtitles=True, wait=True)`.
5. Em modo `curation`, publicar os Shorts gerados em `vf_curation(category="short")` para visualização na UI.
6. Rodar `vf_qa(action="final")` em cada Short (exceto se preview rápido com `qa_mode="skip"`).
