# VideoFlow 4.9.0

Real-Media Gate: decupagem sem perda de fala, legendas ASS reais, overlays
visíveis no MP4/FCPXML, áudio na duração da timeline e Windows com visão.

## Decupagem

- Sentenças mantidas preservam `Sentence.id`; uma tomada descartada não absorve
  nem renumera a próxima tomada boa.
- `discard_sentences([0,1])` + `run_full` mantém `[2..N]`.
- Sentenças sem words usam `[start_sample, end_sample]` na união VAD/ASR.
- `decupage_diff.md` mostra cada bloco cortado, duração e texto removido.

## Legendas e QA

- `.ass` e `.srt` saem da mesma lista de cues.
- `empty_ass_events` falha explicitamente quando não há `Dialogue:`.
- JSON lido como `utf-8-sig`; legendas e JSON escritos em UTF-8.
- `vf_qa` aceita `fast`, `full`, `preview`, `skip` e `off`.
- Nenhum erro MCP vazio: sempre há `error_code`, `message`, `last_frame` e
  `stack_tail`.

## Overlays e NLE

- Overlays `beatmap-*` são substituídos, nunca duplicados.
- Imagens usam Ken Burns suave `1.00 → 1.06` antes das legendas.
- MP4 compõe `state.overlays`; FCPXML exporta B-roll com `broll_clips` correto.
- Render NVENC reporta `device="local_cuda"` e `encoder="h264_nvenc"`.

## Áudio

- `dialogue_timeline.wav` é reconstruído da timeline editada.
- Duração do áudio = duração da timeline, nunca da fonte bruta.
- Música resolve parâmetro explícito → `music_tracks` do beatmap →
  `audio/music/music-bed.wav`.
- Beatmap com música ausente falha com `AudioFinalizeError`.

## Windows e MCP

- `assets.screen_capture` usa o resolvedor único de Edge/Chrome/Playwright.
- `vf_style(action="apply")` registrado.
- `vf_scenes(action="manifest")` auto-analisa cache ausente.
- `broll.plan_master` inclui assets aprovados `kind="broll"`.
- `opencv-python-headless` e `scenedetect` entram no build Windows/release.

## Instaladores Windows

Os assets abaixo são gerados no empacotamento da release:

- `videoflow-4.9.0-windows-x86_64.exe`
- `VideoFlow-4.9.0-windows-x64-cuda.zip`
- `VideoFlow-Windows-GPU-Worker-4.9.0.zip`

## Uso no Windows

```powershell
# portátil
.\videoflow-4.9.0-windows-x86_64.exe doctor
.\videoflow-4.9.0-windows-x86_64.exe

# CUDA
Expand-Archive VideoFlow-4.9.0-windows-x64-cuda.zip -DestinationPath VideoFlow-CUDA
.\VideoFlow-CUDA\videoflow-windows-cuda\videoflow.exe doctor
```

## Validação

- `ruff check src packages scripts tests`: limpo.
- `pytest -q`: 3160 passed, 1 skipped, 1 xfailed; cobertura 96,72%.
- `pytest -m media`: 37 passed, 2 skipped.
- UI: `svelte-check` 0 erros/0 warnings; 55 testes.
