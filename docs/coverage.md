# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## Current working tree (2.41.0)

| Layer | Hit | Total | Cover | 2.12 target | 2.13 target |
| --- | ---: | ---: | ---: | ---: | ---: |
| api | 2,667 | 2,868 | 93.0% | 75% | 85% |
| jobs | 631 | 683 | 92.4% | 85% | 90% |
| exporters | 1,157 | 1,205 | 96.0% | 90% | 95% |
| mcp | 1,124 | 1,169 | 96.2% | 80% | 80% |
| steps | 2,922 | 3,022 | 96.7% | — | — |
| application | 8,192 | 8,655 | 94.7% | — | — |
| domain | 1,048 | 1,051 | 99.7% | — | — |
| **full tree** | **20,261** | **21,209** | **95.5%** | — | — |

The full-tree 95% gate is **met**. The release gate (`uv run pytest`) is at
99.4%. Remaining misses are mostly unreachable defensive branches.

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
