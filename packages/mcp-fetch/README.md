# videoflow-mcp-fetch

Isolated MCP package for VideoFlow 2.90 asset acquisition. It exposes four
project-scoped tools:

| Tool | Source |
| --- | --- |
| `fetch_stock_broll` | Pexels or Pixabay videos |
| `fetch_stock_images` | Pexels/Pixabay, or keyless `gallery-dl` |
| `rip_video_segment` | `yt-dlp` section download |
| `fetch_sfx` | Freesound, or a local `VF_SFX_DIR` |

Every download is copied into the project workspace at
`assets/broll`, `assets/images`, or `assets/sfx`, with a metadata sidecar and a
license sidecar next to the media file. Requests are idempotent per
provider/query/parameters, so a repeated call reuses the existing asset and
makes no network request.

## Environment

- `VF_WORKSPACE_ROOT` — workspace parent (default `~/.videoflow/workspaces`).
- `PEXELS_API_KEY`, `PIXABAY_API_KEY` — keyed stock providers.
- `FREESOUND_API_KEY` — Freesound SFX provider.
- `VF_SFX_DIR` — local SFX provider directory.
- `VF_ALLOWED_EXTERNAL_HOSTS` — optional comma-separated allowlist for
  `yt-dlp`/`gallery-dl` URLs.
- `VF_GALLERY_DL_URL_TEMPLATE` — optional keyless gallery-dl URL template using
  `{query}`; otherwise the query must itself be an http(s) URL.

## Run

```bash
uv run --package videoflow-mcp-fetch videoflow-mcp-fetch
```

The server speaks MCP over stdio.

## Development

```bash
pytest tests/unit/test_mcp_fetch.py --no-cov
ruff check packages/mcp-fetch tests/unit/test_mcp_fetch.py
```
