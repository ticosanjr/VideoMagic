<!-- videoflow:opencode:start -->
# VideoFlow × OpenCode

Workspace preparado pelo VideoFlow {{VERSION}}.

## Protocolo

1. **Estilo, workflow e modo primeiro.** Antes de decupar, liste
   `./presets/*.md` e
   `./.opencode/workflows/*.md`, chame `vf_style(action="list")` e pergunte
   Estilo, Workflow e Modo (`curation` ou `autonomous`).
2. **Não comece sem as respostas.** Estilo novo deve ser salvo com
   `vf_style(action="save", workspace_dir="{{TARGET_DIR}}")`.
3. **Use somente tools MCP.** Nunca escreva scripts FFmpeg manuais.
4. **Fluxo determinístico:**
   1. `vf_project` → `vf_ingest` → `vf_style(action="apply")`.
   2. `vf_capabilities`; operações pesadas vão ao Worker Windows.
   3. `vf_decupage(action="review_packet")`: leia **100%** das sentenças e
      identifique retakes/frases repetidas.
   4. `vf_decupage(action="discard_sentences", sentence_ids=[...])`.
   5. `vf_decupage(action="run_full", pacing_profile="tight", wait=True)`.
   6. `vf_scenes` → `vf_transcript(action="editorial_map")`.
   7. Planeje B-roll **somente** em `TALKING_HEAD`; nunca sobre
      `SCREEN_SHARE_*` ou `protected_from_broll`.
   8. Toda imagem entra com `image_to_broll_motion` (`1.00 → 1.06`); nunca
      imagem parada nem zoom maior que `1.08`.
   9. No modo `curation`, publique `vf_curation(action="publish")` com
      `start_sec`, `end_sec`, `spoken_context` e `local_path`; mostre
      `board_url` e pare o turno. No modo `autonomous`, use `auto_select`.
   10. `vf_timeline(action="apply_beatmap")` → `vf_audio(action="master")`.
   11. Preview rápido: `vf_export(action="render", mode="preview",
       qa_mode="skip", wait=True)`.
   12. Entrega: `vf_export(action="bundle", targets=["mp4", "resolve",
       "premiere", "kdenlive"], mode="final")` + `vf_qa(action="final")`.
5. **Siga `_next_step`** retornado pelas tools.
6. **Use apenas nós existentes.** Se um passo não aparecer no catálogo MCP,
   não o invente; escolha o equivalente listado pelo workflow.
7. **Persistência.** Estilo novo/clonado deve ser salvo no catálogo e
   sincronizado em `./presets/<style_id>.md`.
8. **Segurança.** Não grave tokens/API keys; use variáveis de ambiente.
9. **Entrega em uma pasta.** Use
   `vf_run(steps=["delivery.collect"], params={"mode":"copy"})` para
   consolidar em `./VideoFlow_Output/{videos,exports,shorts,scenes}`.
10. **Profile.** `--profile core` no dia a dia; `--profile full` apenas para
    `vf_fx_*` e edição avançada.

## Catálogo

{{STYLE_LIST}}

{{WORKFLOW_LIST}}

Cada estilo fica em `./presets/<style_id>.md`; cada workflow em
`./.opencode/workflows/<workflow_id>.md`.

## Projetos

`VF_WORKSPACE_ROOT` aponta para `{{TARGET_DIR}}/projects`.
Abra cada projeto com `vf_project(action="open", project_id="...")`.

## Regras visuais

- Texto atrás do apresentador: `vf_fx_depth(project_id, asset, start, end)`;
  nunca `remove_background(is_video=True)` no vídeo inteiro.
- Web 3D: `vf_fx_capture` + `vf_fx_motion(engine="hyperframes",
  transparent=True)`, `width_ratio=0.72`, `z=20`.
- Imagem parada: `image_to_broll_motion` com `1.00 → 1.06`; documentário
  `max_static_sec=5.0`, Shorts `2.5`.
- Punch-in em rosto: `1.00 → 1.06`; máximo `1.08`; nunca `1.15`.
- Legendas: `z=40`, blocos de 4–6 palavras, `WrapStyle: 0`, safe-zones
  verticais. Lower third: `bottom_left`, `margin_x=64`, `margin_y=64`, `z=20`.
<!-- videoflow:opencode:end -->
