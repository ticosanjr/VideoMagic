# VideoFlow 4.6.0

Correções de causa-raiz nos 44 sintomas reportados: NVENC e PCM, duração do
export, curadoria visual, decupagem agressiva, contratos MCP, paths/clones e
inicialização 1-clique no Windows.

## Render e áudio

- Flags NVENC vêm apenas de `probe_nvenc()`, sem `-spatial_aq` hardcoded.
- Leitor PCM único para WAV 16/24/32-bit em `domains/audio/pcm_io.py`.
- `audio.finalize` lê `loudnorm` de stdout/stderr e expõe ducking/music gain.
- `audio_source` de mix/final/master reconectado ao render.
- Âncora `fullscreen` disponível para overlays.

## Export, NLE e QA

- Duração da timeline preservada no fps de saída (60 → 30 fps sem perder metade).
- `resolve_render_profile()` centraliza preview/draft/fps e `draft_scale`.
- `qa_mode` aceita `none`/`off`; `review.json` em `needs_review`.
- Nomes canônicos de NLE resolvidos em `exports/` e na raiz do projeto.

## Curadoria

- `local_path` validado, poster de vídeo e preview MP3 leve para WAV pesado.
- `media_url`/`poster_url` com MIME explícito e HTTP `Range`.
- `scene_id` e `local_path` preservados nas decisões.
- Cards de imagem, vídeo, áudio e estilo com retry inline.

## Decupagem

- `run_full`: `ingest → audio.vad → transcribe → speech.asu →
  speech.editorial_clean → retakes.cull → decupage.snap → edit.timeline`.
- `edit.timeline` aceita pacing, usa spans seguros do snap, preserva overlays e
  exige `reset=True` para sobrescrever edição manual.
- Perfil `tight`: `180/200/55/80/500` ms.
- Remove repetições (1.5 s), fragmentos de até 3 palavras e candidatos
  semânticos fracos.
- Segundo passe e retakes distantes com `0.52` / 2 palavras de conteúdo.
- Beatmap preenche `keep_ranges`/`remove_ranges`.

## MCP, paths e clones

- Ação desconhecida retorna `ok: False`, `error_code: "unknown_action"` e
  `valid_actions` em todas as tools.
- `vf_audio(music_path)`, `vf_media(action="search")` e
  `vf_ingest(action="probe")`.
- Cache de modelos invalidado após instalação/remoção.
- Fim de `projects/projects/<slug>`.
- Clones `demo-copy`, `demo-copy-2`, … com `work`/`assets` isolados.
- Vídeo keyless via Wikimedia/Internet Archive e SFX procedural em WAV real.

## Inicialização 1-clique

- `videoflow`/`videoflow.exe` sem subcomando abre o tray ou sobe `serve`
  headless.
- Bootstrap daemon de Silero VAD e Faster-Whisper small com progresso em `jobs`.
- `--no-auto-download` e `VIDEOWFLOW_NO_AUTO_DOWNLOAD=1`.
- Porta livre automática (`span=100`), com bind, conexão e `netstat` validados
  no Windows, e `active_server.json` com a porta real.
- `restart` destacado com timeout de 5 s no PID antigo e `/health` em até 15 s.

## Assets esperados

- `videoflow-4.6.0-linux-x86_64`
- `VideoFlow-4.6.0-x86_64.AppImage`
- `videoflow-4.6.0-windows-x86_64.exe`
- `VideoFlow-4.6.0-windows-x64-cuda.zip`
- `VideoFlow-Windows-GPU-Worker-4.6.0.zip`
- `sbom.json` e `SHA256SUMS`

O modelo Faster-Whisper não vai dentro do zip CUDA; ele é baixado no primeiro
uso em `videoflow-data/models`, ou automaticamente pelo bootstrap do executável.

## Uso no Windows

```powershell
# extraia o zip CUDA em uma pasta gravável e dê duplo clique em videoflow.exe
.\videoflow.exe doctor
.\videoflow.exe serve --open
```

## Validação

- `ruff check src packages tests scripts`: limpo.
- `pytest -q`: 3092 passed, 1 skipped, 1 xfailed; cobertura 96,79%.
- `pytest -m media`: 29 passed, 2 skipped.
- Fase P2-1: 64 passed.
- UI: `svelte-check` 0 erros/0 warnings, 55 testes, build concluído.
- `uv lock --check`: 199 pacotes resolvidos.
