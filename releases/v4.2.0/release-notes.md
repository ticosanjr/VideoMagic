# VideoFlow 4.2.0

Release de hardening estrutural: correções fail-closed no core, LLM e GPU
worker, perfis MCP estritos e remoção de pipelines/artefatos duplicados.

## Destaques

- AppImage e executável Windows empacotam o tray (`pystray`, Pillow e
  `python-xlib` no Linux), restaurando o ícone ao abrir o VideoFlow.
- WAV 24-bit com RMS real, QA lendo `exports/qa/`, SSE sem bloquear threads e
  códigos HTTP v4 estáveis.
- LLM com budget e circuit breaker antes do HTTP, cache de status do OpenCode e
  DeepSeek somente com rede permitida e API key.
- GPU worker com registro único de handlers, preflight dinâmico, fail-closed em
  `remote`, fallback `auto` explícito e NVENC com fontes/10-bit.
- MCP com guard único, `did_you_mean`, `core` = 16 tools e `full` = 21.
- Shorts com uma fonte única, brand kit consolidado e estilos somente em
  `src/videoflow/styles/`.
- Wheels antigos, recipes legadas e scripts históricos removidos.

## Artifacts

Os binários Linux/Windows, o kit do GPU worker e o SBOM são publicados como
assets desta release. Checksums estão em `SHA256SUMS`.

## Upgrade notes

- Rulebooks antigos usam a chave legada de kit; a leitura migra para
  `brand_kit` automaticamente e a próxima escrita emite o nome novo.
- O perfil MCP `core` é o padrão; use `--profile full` para FX e estilo.
- O kit Windows agora empacota `videoflow_gpu_worker-4.2.0` e
  `vf_shared-4.2.0`.

## Validation

- 2.992 testes verdes (1 skipped, 1 xfailed), ruff limpo, media tests verdes.
