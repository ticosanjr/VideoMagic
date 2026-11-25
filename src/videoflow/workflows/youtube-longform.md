---
schema_version: 1
version: 2
workflow_id: youtube-longform
name: "YouTube Longform Inteligente (16:9)"
description: "Decupagem assistida pelo OpenCode, análise de cenas, B-roll contextual, curadoria visual e entrega MP4 + 3 NLEs."
aspect_ratio: "16:9"
platforms:
  - youtube
inputs:
  - source
steps:
  - id: ingest
    node: ingest
    purpose: "Ingestão CFR, probe e WAV 48 kHz"
    requires_approval: false
  - id: decupage_prep
    node: decupage.snap
    purpose: "VAD + transcrição + ASU + pacote de revisão de retakes"
    requires_approval: false
  - id: scenes
    node: scene.analyze
    purpose: "Detecção de cenas, rostos e proteção de screen-share"
    requires_approval: false
  - id: curation
    node: curation.prepare
    purpose: "Curadoria visual de B-roll, imagens, música e SFX"
    requires_approval: true
  - id: audio
    node: audio.finalize
    purpose: "Mix de trilha (loop) + SFX + ducking + loudnorm 2-pass -16 LUFS"
    requires_approval: false
  - id: captions
    node: captions.plan
    purpose: "Legendas alinhadas por palavra na timeline editada"
    requires_approval: false
  - id: export
    node: export.nle
    purpose: "Render MP4 (preview ou final) + Resolve + Premiere + Kdenlive"
    requires_approval: true
approvals:
  - curation
  - final_export
default_style: "canal-paula-long"
compatible_styles:
  - canal-paula-long
  - canal-rafael-tech
  - lf-cinema-doc-25d
export_targets:
  - mp4_youtube
  - resolve
  - premiere
  - kdenlive
updated_at: "2026-11-25T12:00:00Z"
---

# YouTube Longform Inteligente

## Sequência Obrigatória MCP

1. Perguntar **Estilo**, **Modo (`curation` vs `autonomous`)** e se deseja **Preview 540p primeiro**.
2. `vf_project(action="init")` → `vf_ingest` → `vf_style(action="apply")`.
3. **Decupagem inteligente (nunca pular):**
   - Chamar `vf_decupage(action="review_packet")`; ler **100% das sentenças** e identificar retakes/frases repetidas (inclusive distantes).
   - Aplicar `vf_decupage(action="discard_sentences")` e rodar `vf_decupage(action="run_full", pacing_profile="tight", wait=True)`.
4. **Mapeamento cena + fala:** Rodar `vf_scenes` e `vf_transcript(action="editorial_map")`. Selecionar slots de B-roll **somente** em cenas `TALKING_HEAD` onde a imagem/clipe ilustra exatamente a frase falada.
5. **Assets sem aleatoriedade:** Buscar com `vf_media(action="search")` ou gerar imagens temáticas; validar relevância do título/duração antes de baixar; aplicar `image_to_broll_motion` (`1.00→1.06`) em toda imagem; aprovar licenças via `vf_media(action="approve_license")`.
6. **Curadoria:** No modo `curation`, publicar `vf_curation(action="publish")` com `start_sec`, `end_sec`, `spoken_context` e `local_path`, mostrar o link da UI e **parar o turno**; no modo `autonomous`, usar `auto_select`.
7. **Montagem & Áudio:** Aplicar `vf_timeline(action="apply_beatmap")` (punch-in máx. `1.07`) → `vf_audio(action="master")` (já com música e SFX).
8. **Entrega:** Se solicitado preview rápido, rodar `vf_export(action="render", mode="preview", qa_mode="skip")`; após aprovação, rodar `vf_export(action="bundle", targets=["mp4", "resolve", "premiere", "kdenlive"], mode="final")` + `vf_qa(action="final")`.
