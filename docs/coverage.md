# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## Current working tree (2.90.0)

Measured with the release-gate omit list disabled. The full unit/contract run is
**2,342 passed, 2 skipped, 1 xfailed**.

| Layer | Hit | Total | Cover |
| --- | ---: | ---: | ---: |
| api | 2,849 | 2,951 | 96.54% |
| adapters | 1,416 | 1,498 | 94.53% |
| application | 16,207 | 17,187 | 94.30% |
| engine | 1,097 | 1,164 | 94.24% |
| exporters | 1,253 | 1,334 | 93.93% |
| mcp | 683 | 726 | 94.08% |
| steps | 9,433 | 9,897 | 95.31% |
| domain | 1,434 | 1,450 | 98.90% |
| cli/runtime/core/plugin | 485 | 505 | 96.04% |
| **full tree (statements)** | **35,557** | **37,427** | **95.00%** |
| **full tree (branches)** | **8,919** | **10,358** | **86.11%** |

The 2.85 agent-profile refactor keeps the full-tree statement target met. The
configured release gate remains at 98% on its selected source set. Remaining
misses are defensive branches for optional backends, offline providers, and
platform-specific tray/notifier code.

## Current working tree (2.58.5)

| Layer | Hit | Total | Cover | 2.12 target | 2.13 target |
| --- | ---: | ---: | ---: | ---: | ---: |
| api | 2,792 | 3,037 | 91.9% | 75% | 85% |
| jobs | 631 | 683 | 92.4% | 85% | 90% |
| exporters | 1,189 | 1,239 | 96.0% | 90% | 95% |
| mcp | 1,126 | 1,172 | 96.1% | 80% | 80% |
| steps | 3,316 | 3,460 | 95.8% | — | — |
| application | 9,658 | 10,239 | 94.3% | — | — |
| domain | 1,048 | 1,051 | 99.7% | — | — |
| **full tree** | **22,342** | **23,515** | **95.01%** | — | — |

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
