# VideoFlow 4.4.0

Decupagem perfeita, Shorts prontos para publicar, MCP determinístico e execução
nativa no Windows 11 com CUDA/NVENC local.

## Decupagem

- União `VAD ∪ ASR`: fala transcrita com `probability >= 0.45` nunca é cortada
  como silêncio.
- Todo corte acima de 15s entra em `decupage/report.json` com RMS, contagem de
  palavras e `requires_review`.
- Pads de 90ms/150ms após o snap acústico.
- `vf_decupage(action="run_full")` executa a ordem canônica e retorna
  `flagged_long_cuts` e `beat_map_path`.
- `BeatMapPlan` v2 aplicado diretamente por `vf_timeline` via `beat_map_path`.

## Shorts e curadoria

- `count` respeitado, `speech_ratio` na janela editada e preferência por câmera
  em vez de screen-share.
- Legendas queimadas por padrão (`burn_subtitles=True`) com sidecar `.ass`.
- `time_basis` `edited`/`source` e rejeição de clipes abaixo de 3s.
- Categorias `short` e `cut_review` no board, com player de vídeo.

## Áudio e entrega

- Alvo único: `-16 LUFS ± 1.5`, `TP=-2.0` no `loudnorm` e gate de `-1.0 dBTP`.
- `audio.finalize` automático antes do export quando `final_mix.wav` não existe.
- Entrega isolada por projeto em `VideoFlow_Output/{project_slug}/{categoria}`.

## MCP

- **18 tools no perfil `core` / 22 no `full`**; `vf_style` agora é core.
- `vf_project(create|new)`, `output` opcional e retorno de `project_id` + `uuid`.
- Slugs, UUIDs e nomes resolvidos em todas as tools e recursos.
- `vf_run` distribui `params` por step e aceita `step_params`.
- `vf_jobs(wait)` retorna payload plano com `result`, `error` e `artifacts`.
- `expected_fields` em erros de schema e `vf_export` sempre estruturado.

## Windows 11 nativo

- Caminhos de filtro FFmpeg escapados como `C\:/...`.
- Fontes de `%WINDIR%\Fonts`.
- Serviços sem `/proc`/`killpg`; lock cross-process com `msvcrt`.
- Detecção local de CUDA: Faster-Whisper em `cuda`/`float16` e FFmpeg em
  `h264_nvenc`/`yuv420p` sem NVDEC em fontes 10-bit.
- `doctor` mostra GPU local, NVENC e fontes.

## Assets

- `videoflow-4.4.0-linux-x86_64`: binário Linux onefile.
- `VideoFlow-4.4.0-x86_64.AppImage`: AppImage Linux.
- `videoflow-4.4.0-windows-x86_64.exe`: executável Windows portátil.
- `VideoFlow-4.4.0-windows-x64-cuda.zip`: bundle Windows `onedir` com
  Faster-Whisper, CTranslate2, DLLs CUDA/cuDNN e `VideoFlow.cmd`.
- `VideoFlow-Windows-GPU-Worker-4.4.0.zip`: kit opcional do worker GPU.
- `sbom.json` e `SHA256SUMS`.

O modelo `faster-whisper-large-v3-turbo` não vai dentro do zip CUDA; ele é
baixado no primeiro uso em `videoflow-data/models`.

## Uso no Windows

```powershell
# extraia o zip CUDA em uma pasta gravável
.\VideoFlow.cmd doctor
.\VideoFlow.cmd serve --open
```

## Validação

- `ruff`: limpo.
- `pytest -q`: 2960 passed, 1 skipped, 1 xfailed; cobertura 96,78%.
- `pytest -m media`: 29 passed, 2 skipped.
- UI: `svelte-check` 0 erros/0 warnings, 53 testes, build concluído.
- Smoke Windows: `version`, `doctor`, `mcp --profile core --list-tools`,
  `serve`, `/health` e `/api/v1/curation/boards`.
