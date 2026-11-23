# VideoFlow 4.3.1

Correção do portable Windows e publicação do build CUDA com Whisper.

## Corrigido no Windows

- O executável 4.3.0 falhava ao iniciar com `ModuleNotFoundError: No module named 'fcntl'`.
  O lock de projeto e o lock de instância agora usam `msvcrt` no Windows.
- O import obrigatório de `resource` foi removido.
- `stop`, `cleanup`, tray, FFmpeg e serviços agora encerram processos com
  `taskkill`/`Popen.terminate` no Windows.
- `status` e a limpeza da porta 8765 detectam o processo dono via
  `netstat -ano`/`tasklist`.
- O CI Windows agora inicia `serve`, consulta `/health`, executa `status` e
  `stop`; builds quebrados deixam de passar.

## Build CUDA com Whisper

Asset adicional:

```text
VideoFlow-4.3.1-windows-x64-cuda.zip
```

Inclui Faster-Whisper, CTranslate2 e DLLs CUDA/cuDNN. O modelo
`faster-whisper-large-v3-turbo` fica fora do executável e é baixado no primeiro
uso pelo `VideoFlow.cmd` em `videoflow-data/models`.

## Uso

```powershell
# extrair o zip em uma pasta gravável
.\VideoFlow.cmd doctor
.\VideoFlow.cmd serve --open
```

O modelo usa `device=cuda` e `compute_type=int8_float16` por padrão.

## Validação

- `ruff`: limpo
- `pytest -q`: 2.911 passed, 1 skipped, 1 xfailed
- cobertura: 96,8%
- `pytest -m media`: 29 passed, 2 skipped
- Windows CI: `version`, `doctor`, `models list`, `mcp --help`, `serve`,
  `/health`, `status`, `stop`
