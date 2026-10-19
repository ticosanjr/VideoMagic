# Operator manual

Installation, models, secrets, ports, backups, and recovery for one machine.

## 0. Portable build (no installation)

If you have the onefile artifact, skip the development setup below:

```bash
./videoflow doctor
./videoflow demo -o ./demo
./videoflow run /media/interview.mp4 -o ./interview-edit
./videoflow serve
```

- FFmpeg/FFprobe are bundled when the build used `--with-ffmpeg`.
- Data goes to `videoflow-data/` next to the executable. Override with
  `VIDEOWFLOW_HOME`.
- Windows: `videoflow.exe`, unsigned, SmartScreen may warn.
- Full details: [portable manual](portable.md).

The rest of this manual covers the development installation, models, and
operations.

## 1. Requirements

| Component | Version | Required |
| --- | --- | --- |
| Python | 3.11+ (3.12 recommended) | yes |
| uv | current | yes |
| FFmpeg + FFprobe | 6.x or 7.x | yes |
| Node | 20 LTS+ | for the UI |
| NVIDIA driver + CUDA | optional | for GPU inference |
| Resolve / Premiere / Kdenlive | see compatibility | for manual QA |

Verify:

```bash
python3 --version
uv --version
ffmpeg -version | head -1
ffprobe -version | head -1
node --version
```

## 2. Install

```bash
git clone <repository> VideoMagic
cd VideoMagic
uv sync --extra dev
uv run pytest
```

The test suite does not download a model and does not require a GPU.

Start:

```bash
uv run videoflow-api
curl -s http://127.0.0.1:8765/health
```

The API binds to `127.0.0.1:8765`. MCP over HTTP is at `/mcp`.

## 3. UI

```bash
cd ui
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The dev server proxies `/api` to the API.

For a static build:

```bash
npm run build
```

Serve `ui/build/` behind the API or a local static server. Do not expose it to a
network.

## 4. Models

Nothing is downloaded at install.

| Engine | Artifact | Approx. size | Where |
| --- | --- | --- | --- |
| Silero VAD | ONNX | ~2 MB | configured model dir |
| Faster-Whisper `small` | CTranslate2 | ~500 MB | model cache |
| Faster-Whisper `medium` | CTranslate2 | ~1.5 GB | model cache |
| Faster-Whisper `large-v3` | CTranslate2 | ~3 GB | model cache |

Record the digest of each artifact you install. Set it in
`retakes.model_artifact_digest` / the Whisper config so the cache invalidates when
the artifact changes.

The first run with a missing model fails with the expected path. It does not
silently download.

## 5. GPU

CPU is the default. To opt in:

1. Install a CUDA-capable PyTorch/CTranslate2 stack compatible with your driver.
2. Set `transcribe.device=cuda`, `compute_type=float16`.
3. Set the VAD runtime to CUDA if supported.
4. Run a one-minute clip and measure.
5. Keep `small` until quality demands more.

If CUDA is requested but unavailable, the run fails. That is deliberate; a silent
CPU fallback makes an ETA lie.

## 6. Secrets

```bash
mkdir -p ~/.videoflow
umask 077
cat > ~/.videoflow/secrets.env <<'EOF'
VIDEOWFLOW_LLM_API_KEY=replace-me
EOF
chmod 600 ~/.videoflow/secrets.env
```

Or export the variable in the process environment. Never put a key in a preset, a
project, a revision, a command line, or a screenshot.

With Ollama or LM Studio, leave the key empty; the local endpoint needs none.

## 7. Allowed roots

The API and MCP refuse a path outside the configured roots:

```bash
export VIDEOWFLOW_ALLOWED_ROOTS="/media:/home/editor/projects"
```

On Windows, separate entries with `;`. Without the variable, home, the current
directory, and the portable data directory are allowed.

Do not set the root to `/` or `C:\`. It defeats the jail.

## 8. Project directory

```
<project>/.videoflow/
  project_state.json
  revisions/        # append-only
  cache/            # content-addressed, safe to delete
  work/             # source.wav, proxy
  exports/          # NLE files and shorts
```

Back up the source media and `.videoflow/project_state.json`. The cache can be
rebuilt. Revisions are small and worth keeping.

Restore: copy the state back, keep the cache if the hashes still match, then run.

## 9. Logs and diagnostics

- The API logs JSON to stderr.
- Secrets are redacted before emission.
- MCP stdio logs go to stderr; stdout is protocol only.
- To report a bug, include the version, the failing module, the error code, and a
  redacted log. Never include the key or private media.

## 10. Ports and process

| Service | Port | Bind |
| --- | --- | --- |
| API | 8765 | 127.0.0.1 |
| MCP HTTP | 8765 `/mcp` | 127.0.0.1 |
| UI dev | 5173 | 127.0.0.1 |
| LLM (Ollama) | 11434 | usually localhost |

Check what is listening:

```bash
ss -ltnp | grep -E '8765|5173|11434'
```

One API process per machine is enough. Do not run two against the same project;
the project lock will reject the second job, but the second process still wastes
resources.

## 11. Upgrades

```bash
git pull
uv sync --extra dev
uv run pytest
```

Then:

- schema migration if `schema_version` changed;
- model digest check;
- one short end-to-end run;
- the manual NLE script before a release tag.

## 12. Recovery

| Symptom | Action |
| --- | --- |
| API will not start | Check port 8765, then the log; a corrupt state fails schema validation. |
| Job stuck `running` after a crash | Stop the process, remove the stale lock only after confirming no process is alive, restart. |
| Cache corrupted | Delete `.videoflow/cache/`; it rebuilds. |
| State corrupt | Restore the latest good file from `.videoflow/revisions/`. |
| Export refused | Check the source is online and the export path is inside the project. |
| MCP tool not found | Check the host config points at `uv run videoflow-mcp` and restart the host. |
| Model mismatch after upgrade | Clear the cache for the affected module. |

## 13. Disk

A 60-minute 4K source plus PCM, proxy, cache, and exports can exceed 10 GB. Budget:

- PCM 16 kHz mono: ~115 MB/hour
- proxy 720p: ~1–2 GB/hour
- Whisper model: 0.5–3 GB once
- cache: 1–3× the analyzed media
- exports: tens of MB

Prune `.videoflow/cache/` between projects.

## 14. Uninstall

Delete the project directories and models you downloaded. The Python environment
lives in `.venv/` and `~/.videoflow/` holds presets and secrets. Nothing is
installed system-wide by VideoFlow itself.
