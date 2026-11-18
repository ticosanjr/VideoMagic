<!-- videoflow:opencode:start -->
# VideoFlow × OpenCode

Este workspace foi preparado pelo VideoFlow {{VERSION}}.

## Protocolo obrigatório

1. **Escolha obrigatória de estilo e workflow**: antes de decupar, gerar
   beatmap, renderizar gráficos ou alterar qualquer vídeo, liste
   `./presets/*.md` e `./.opencode/workflows/*.md`, chame
   `vf_style(action="list")` e **pergunte explicitamente ao usuário**, em lista
   numerada, qual Estilo e qual Workflow devem ser usados.
2. **Não comece sem as duas respostas.** Se o usuário quiser um novo estilo,
   clone/extraia a referência e salve com
   `vf_style(action="save", workspace_dir="{{TARGET_DIR}}")`.
3. **Nunca escreva scripts FFmpeg manuais no bash.** Use as tools MCP do
   VideoFlow para ingest, transcrição, beatmap, motion, captura, QA e export.
4. **Fluxo determinístico em 5 etapas**:
   1. `vf_ingest` (CFR + multi-take/multicam) + `transcribe_word_aligned` +
      `session.cull`.
   2. Gerar `beat_map.json` a partir do `.md` do estilo escolhido e **aguardar
      aprovação humana** antes de renderizar gráficos.
   3. Montagem atômica com `vf_timeline(action="apply_beatmap")`,
      `render_motion_graphic` (`draft_scale=0.5`) e `capture_web_or_screen`
      ou `mcp-vf-media-fetch`.
   4. Auditoria visual obrigatória com `vf_qa(action="inspect")` e correção
      antes de mostrar o rascunho.
   5. Exportar com `vf_exports(action="bundle", targets="all")` para
      YouTube MP4, Resolve `.fcpxml`, Premiere `.xml` e Kdenlive MLT; registrar
      feedback com `vf_style(action="learn_rule")`.
5. **Persistência de estilo**: qualquer estilo novo ou clonado deve ser salvo no
   catálogo e sincronizado em `./presets/<style_id>.md`.
6. **Segurança**: não grave tokens/API keys em arquivos do workspace. Use
   variáveis de ambiente (`VF_GPU_WORKER_TOKEN`, etc.).

## Estilos disponíveis no catálogo

{{STYLE_LIST}}

## Workflows disponíveis

{{WORKFLOW_LIST}}

## Comandos

- `/decupar <fonte>` — ingest, transcrição, cull e timeline base.
- `/beatmap <estilo>` — gera e revisa o manifesto de cenas.
- `/salvar-estilo <nome-ou-url>` — cria/clona e salva um estilo.
- `/exportar` — bundle MP4 + Resolve + Premiere + Kdenlive.

## Projetos

`VF_WORKSPACE_ROOT` aponta para `{{TARGET_DIR}}/projects`.
Cada projeto é aberto com `vf_project(action="open", project_id="...")`.
<!-- videoflow:opencode:end -->
