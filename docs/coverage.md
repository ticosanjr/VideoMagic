# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## Current working tree (after 2.20.0)

| Layer | Hit | Total | Cover | 2.12 target | 2.13 target |
| --- | ---: | ---: | ---: | ---: | ---: |
| api | 2,282 | 2,681 | 85.1% | 75% | 85% |
| jobs | 546 | 610 | 89.5% | 85% | 90% |
| exporters | 1,130 | 1,189 | 95.0% | 90% | 95% |
| mcp | 932 | 1,161 | 80.3% | 80% | 80% |
| steps | 2,586 | 2,809 | 92.1% | — | — |
| application | 7,477 | 7,997 | 93.5% | — | — |
| domain | 1,026 | 1,028 | 99.8% | — | — |
| **full tree** | **17,885** | **20,081** | **89.1%** | — | — |

The full-tree 95% gate remains open. The remaining 2,196 missed statements are
concentrated in `api/routes.py` (375), `cli.py` (337),
`mcp_server/server.py` (223), and `adapters/ffmpeg.py` (180).

## 2.20.0 baseline (historical)

| Layer | Hit | Total | Cover |
| --- | ---: | ---: | ---: |
| api | 2,280 | 2,681 | 85.0% |
| jobs | 554 | 610 | 90.8% |
| exporters | 1,130 | 1,189 | 95.0% |
| mcp | 932 | 1,161 | 80.3% |
| steps | 2,218 | 2,807 | 79.0% |
| application | 6,552 | 7,977 | 82.1% |
| domain | 1,019 | 1,028 | 99.1% |
| **full tree** | **16,434** | **20,059** | **81.9%** |
