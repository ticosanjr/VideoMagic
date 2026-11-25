# VideoFlow 4.8.0

Export confiável, áudio realmente mixado, decupagem protegida, Shorts centrados
e QA/MCP fail-closed.

## Setup do OpenCode

- O campo de pasta do workspace agora tem um navegador embutido com unidades,
  raízes permitidas, navegação por subpastas e caminho editável.
- O seletor nativo do Windows usa PowerShell/WinForms, com fallback para
  Tkinter quando necessário.

## Export e preview

- `burn_subtitles=True` aplica o `.ass` no passe final e falha explicitamente se
  a legenda estiver ausente ou vazia.
- Fontes ficam isoladas em `work/fonts`, sem o scan lento de `C:/Windows/Fonts`.
- Preview e Shorts gravam `fps=30` estrito (`30/1`) com `-fps_mode cfr`.
- NVENC entra quando o probe local aprova o encoder; `libx264` é o fallback
  explícito.
- Preview e render final herdam `audio/final_mix.wav` quando ele existe.

## Áudio

- Música autodetectada em `audio/music/music-bed.wav`, com loop e ducking
  `sidechaincompress`.
- SFX de `beat_map.json` e `audio/sfx-plan.json` mixados por timestamp e ganho.
- Loudness corrigido para `-16.0 ± 0.6 LUFS` com passe linear
  `volume` + `alimiter`.
- Eventos além da timeline são clampados com warning; quando nada pode ser
  mixado, o estágio falha com `AudioFinalizeError`.

## Decupagem e legendas

- `faster-whisper-large-v3-turbo` em `cuda`/`float16` quando há GPU local,
  `small`/`int8` em CPU, com auto-install do modelo escolhido.
- `rms_energy_guard()` protege palavras reais expandindo bordas em passos de
  10 ms sobre energia vocal.
- `apply_beatmap(apply_cuts=False)` não substitui mais os segmentos da timeline;
  aplica apenas overlays, SFX, transições, legendas e zooms.
- Legendas descartam sentenças removidas, ignoram palavras fora dos segmentos
  mantidos e deduplicam cues similares.

## Shorts

- Detecção facial com mediana de 7 frames, MediaPipe e Haar multi-escala.
- Crop aplicado diretamente na fonte com `crop_w:crop_h:crop_x:crop_y`.
- Rosto em `cx=0.72` em 1920×1080 gera `crop_w=608` e `crop_x=1078`.
- ASS com `WrapStyle: 0`, `MarginL/R: 140` e `\an5\pos(540,Y)`.
- `vf_shorts` expõe `batch`/`select`/`plan`, `time_basis`, `burn_subtitles` e
  `wait`.

## QA e MCP

- `vf_export(action="validate")` usa `<projeto>/exports` absoluto.
- Nenhum erro MCP volta vazio; exceções genéricas usam o nome do tipo e
  incluem `last_frame`/`stack_tail`.
- B-roll fullscreen atrás das legendas não gera `caption_overlap`.
- Edge, Chrome e Chromium do Playwright são localizados nos caminhos padrão do
  Windows.
- `auto_select` mantém múltiplos slots de B-roll por timestamp.

## Instaladores Windows

Os assets abaixo são gerados no empacotamento da release:

- `videoflow-4.8.0-windows-x86_64.exe`
- `VideoFlow-4.8.0-windows-x64-cuda.zip`
- `VideoFlow-Windows-GPU-Worker-4.8.0.zip`

## Uso no Windows

```powershell
# portátil
.\videoflow-4.8.0-windows-x86_64.exe doctor
.\videoflow-4.8.0-windows-x86_64.exe

# CUDA
Expand-Archive VideoFlow-4.8.0-windows-x64-cuda.zip -DestinationPath VideoFlow-CUDA
.\VideoFlow-CUDA\videoflow-windows-cuda\videoflow.exe doctor
```

## Validação

- `ruff check src packages tests scripts`: limpo.
- `pytest -q`: 3147 passed, 1 skipped, 1 xfailed; cobertura 96,72%.
- `pytest -m media`: 32 passed, 2 skipped.
- UI: `svelte-check` 0 erros/0 warnings; 55 testes.
