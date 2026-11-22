<!-- videoflow:opencode:start -->
# VideoFlow × OpenCode

Workspace preparado pelo VideoFlow {{VERSION}}.

## Protocolo obrigatório

1. **Estilo e workflow primeiro.** Antes de decupar, gerar beatmap, renderizar
   gráficos ou alterar qualquer vídeo, liste `./presets/*.md` e
   `./.opencode/workflows/*.md`, chame `vf_style(action="list")` e pergunte ao
   usuário, em lista numerada, qual Estilo e qual Workflow usar.
2. **Não comece sem as duas respostas.** Se o usuário quiser um estilo novo,
   clone/extraia a referência e salve com
   `vf_style(action="save", workspace_dir="{{TARGET_DIR}}")`.
3. **Nunca escreva scripts FFmpeg manuais.** Use as tools MCP do VideoFlow
   para ingest, transcrição, beatmap, motion, captura, QA e export.
4. **Fluxo determinístico:**
   1. `vf_ingest` + `vf_transcript` + `speech.editorial_clean` +
      `retakes.cull`.
   2. `vf_decupage` gera o `beat_map.json`; aguarde aprovação humana.
   3. `vf_timeline(action="apply_beatmap")` + `vf_fx_motion` +
      `vf_fx_capture` quando o estilo pedir.
   4. Audite com `vf_qa` e corrija antes de mostrar o rascunho.
   5. `vf_export(targets="all")` para YouTube, Resolve, Premiere e Kdenlive.
5. **Persistência de estilo.** Estilo novo ou clonado deve ser salvo no catálogo
   e sincronizado em `./presets/<style_id>.md`.
6. **Segurança.** Não grave tokens/API keys no workspace; use variáveis de
   ambiente (`VF_GPU_WORKER_TOKEN`, etc.).
7. **Entrega em uma pasta.** Ao concluir, sem outro destino pedido, rode
   `vf_exec(action="step", step_id="delivery.collect", params={"mode":"copy"})`
   para consolidar em `./VideoFlow_Output/{videos,exports,shorts,scenes}`.
   O MCP aceita qualquer caminho e nunca bloqueia uma entrega por causa da
   pasta de saída.
8. **Offload pesado.** Use `compute_policy="auto"` ou `"remote"` para ASR,
   alinhamento forçado, matte, NVENC, scene analysis e Shorts quando o worker
   Windows estiver disponível; reporte `degraded` se houver fallback local.
9. **Profile enxuto.** Use `--profile core` (16 tools) no dia a dia e
   `--profile full` (21) apenas quando precisar de FX ou estilo.

## Catálogo

{{STYLE_LIST}}

{{WORKFLOW_LIST}}

Cada estilo fica em `./presets/<style_id>.md`; cada workflow em
`./.opencode/workflows/<workflow_id>.md`. Liste os diretórios, chame
`vf_style(action="list")` e pergunte qual par usar.

## Projetos

`VF_WORKSPACE_ROOT` aponta para `{{TARGET_DIR}}/projects`.
Abra cada projeto com `vf_project(action="open", project_id="...")`.

## Regras visuais

- Texto atrás do apresentador: `vf_fx_depth(project_id, asset, start, end)`;
  nunca `remove_background(is_video=True)` no vídeo inteiro.
- Web 3D: `vf_fx_capture` + `vf_fx_motion(engine="hyperframes",
  transparent=True)` e `width_ratio=0.72`, `z=20`.
- Imagem parada: use `image_to_broll_motion` ou `vf_fx_parallax`; em
  documentário `max_static_sec=5.0`, em Shorts `2.5`.
- Punch-in em rosto: `1.00 → 1.08`; nunca acima de `1.10`.
- Legendas: `z=40`, blocos de 4–6 palavras, `WrapStyle: 0`, dentro das
  safe-zones verticais.
- Lower third: `anchor="bottom_left"`, `margin_x=64`, `margin_y=64`, `z=20`.

## Ordem operacional

1. Ingest, transcrição, limpeza editorial e cull.
2. Estilo aprovado + `vf_decupage`; valide com `vf_preview`.
3. Compostos (`vf_fx_depth`, `vf_pip`, `vf_fx_parallax`, `vf_fx_motion`).
4. Timeline + overlays com âncoras e `z` explícitos.
5. `vf_preview`, `vf_qa`, correções e então `vf_export` + `vf_qa_final`.
   Publique apenas com status `succeeded`.
<!-- videoflow:opencode:end -->
