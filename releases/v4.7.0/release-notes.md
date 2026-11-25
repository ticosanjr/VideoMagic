# VideoFlow 4.7.0

Edição inteligente guiada pelo OpenCode: decupagem assistida, mapa editorial,
contratos MCP completos, áudio idempotente, stock filtrado e catálogo enxuto.

## Decupagem assistida

- `vf_decupage(action="review_packet")` devolve 100% das sentenças com flags
  `[DISCARDED]` e `[SUSPECT_RETAKE]`.
- `vf_transcript(action="editorial_map")` mapeia fala, cena, layout e keyframe
  na timeline editada.
- Guarda fonética de 75/115 ms impede corte de palavras reais.
- `session.cull` restaura a timeline em vez de apagar todos os clipes.
- Pacing `tight` `260/260/75/115/650`; `balanced` `380/400/90/130/900`.
- Punch-in padrão `1.06`, teto `1.08`.

## MCP

- `wait=True` retorna o job terminal.
- `vf_timeline(action="time_map")` e paginação até 500.
- `vf_transcript` corrige 104/104 sentenças.
- Licenças aprovadas em disco desbloqueiam `apply_beatmap`.
- `vf_export(action="mp4")` e `qa_mode="skip"`.
- Prompt `videoflow_full_test` e resource `vf://tests/full-540p` instruem o
  OpenCode no teste completo rápido.

## Áudio

- `dialogue_timeline.wav` como entrada canônica; nunca `final.wav`.
- Escrita atômica e re-execução idempotente.
- Loop de música com fade-out de 2.5 s.
- SFX de `beat_map.json` e `sfx-plan.json` mixados por timestamp/gain.

## Stock e curadoria

- Stock keyless filtrado por 120 s, 80 MB e relevância 0.35.
- Auto-trim para 8 s em 1080p.
- Ken Burns de imagens em `1.00 → 1.06`.
- Curadoria com `start_sec`, `end_sec`, `spoken_context` e `note`.

## Catálogo

- 6 estilos oficiais: `canal-paula-long`, `canal-paula-reels`,
  `canal-rafael-tech`, `lf-cinema-doc-25d`, `sr-viral-depth-split`,
  `sr-feed-4x5-card`.
- 5 workflows com nós MCP válidos.
- `AGENTS.md` em 74 linhas.

## Instaladores Windows

- `videoflow-4.7.0-windows-x86_64.exe` — executável portátil 1-clique; duplo
  clique inicia o Tray, escolhe porta livre e baixa os modelos essenciais.
- `VideoFlow-4.7.0-windows-x64-cuda.zip` — bundle onedir com CUDA,
  Faster-Whisper/CTranslate2 e `VideoFlow.cmd` para máquinas NVIDIA.
- `VideoFlow-Windows-GPU-Worker-4.7.0.zip` — kit opcional do worker GPU.

## Assets Linux

- `videoflow-4.7.0-linux-x86_64`
- `VideoFlow-4.7.0-linux-x86_64.tar.zst`
- `VideoFlow-4.7.0-x86_64.AppImage`
- `sbom.json`, `SHA256SUMS`, `manifest.json`

## Uso no Windows

```powershell
# portátil
.\videoflow-4.7.0-windows-x86_64.exe doctor
.\videoflow-4.7.0-windows-x86_64.exe

# CUDA
Expand-Archive VideoFlow-4.7.0-windows-x64-cuda.zip -DestinationPath VideoFlow-CUDA
.\VideoFlow-CUDA\videoflow-windows-cuda\videoflow.exe doctor
```

## Validação

- `ruff check src packages tests scripts`: limpo.
- `pytest -q`: 3127 passed, 1 skipped, 1 xfailed; cobertura 96,72%.
- `pytest -m media`: 29 passed, 2 skipped.
- UI: `svelte-check` 0 erros/0 warnings, 55 testes, build concluído.
