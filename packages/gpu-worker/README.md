# videoflow-gpu-worker

Isolated GPU inference worker for VideoFlow 2.90. The main VideoFlow process talks to it over
HTTP and never imports it, so heavyweight GPU dependencies stay out of the desktop runtime.

## Run

```bash
export VF_GPU_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export VF_GPU_WORK_DIR="$HOME/.videoflow/gpu-worker"
videoflow-gpu-worker
```

The worker binds `0.0.0.0:8766` by default. Every endpoint except `GET /health` requires the
`X-VF-Token` header to match `VF_GPU_TOKEN`.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `VF_GPU_TOKEN` | none | Shared token. Non-health requests fail without it. |
| `VF_GPU_HOST` | `0.0.0.0` | Bind host. |
| `VF_GPU_PORT` | `8766` | Bind port. |
| `VF_GPU_WORK_DIR` | `~/.videoflow/gpu-worker` | Artifacts, jobs, and the SQLite store. |
| `VF_GPU_MAX_UPLOAD_MB` | `512` | Per-artifact upload limit. |
| `VF_GPU_MAX_QUEUE` | `16` | Maximum number of queued jobs. |
| `VF_GPU_MODEL_TTL_SEC` | `900` | Idle seconds before a loaded model is unloaded. |
| `VF_GPU_SHARED_ROOT` | none | Root for read-only `shared_inputs` paths. |
| `VF_CHATTERBOX_CMD` | none | TTS command. |
| `VF_ACE_STEP_CMD` | none | Music command. |
| `VF_STABLE_AUDIO_CMD` | none | SFX command. |
| `VF_AUDIO_SEPARATOR_CMD` | none | Stem separation command. |
| `VF_REALESRGAN_CMD` | none | Upscale command. |
| `VF_GPU_COMFYUI_URL` | none | ComfyUI base URL (also `VF_COMFYUI_URL`). |

Commands are split with `shlex` and executed without a shell. `{input}`, `{output}`,
`{output_dir}`, `{work_dir}`, and string params such as `{text}`, `{prompt}`, `{duration}` are
substituted per token. If `{output}` is absent the output path is appended.

## API

- `GET /health` — GPU details, available capabilities, loaded models, queue depth.
- `POST /artifacts` — multipart `file`; returns content-addressed `artifact_id`, `sha256`, `bytes`.
- `POST /jobs/{capability}` — `{params, inputs, shared, shared_inputs}`; returns `{job_id, status}`.
- `GET /jobs/{job_id}` — status, error, and artifact names.
- `GET /jobs/{job_id}/artifact/{name}` — download a job result.
- `DELETE /jobs/{job_id}` — delete the job and its working directory.

Handlers are registered with `app.state.registry.register_handler(capability, handler)`, where
`handler(params, input_paths, work_dir)` returns a list of artifact paths.
