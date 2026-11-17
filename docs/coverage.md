# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## Current working tree (2.91.3)

Measured with the release-gate omit list disabled. The full unit/contract run is
**2,462 passed, 1 skipped, 1 xfailed**.

| Layer | Hit | Total | Cover |
| --- | ---: | ---: | ---: |
| api | 2,934 | 3,039 | 96.54% |
| exporters | 1,532 | 1,601 | 95.69% |
| mcp | 825 | 861 | 95.82% |
| steps | 9,570 | 10,049 | 95.23% |
| application | 17,339 | 18,388 | 94.30% |
| engine | 1,098 | 1,164 | 94.33% |
| domain | 1,502 | 1,518 | 98.95% |
| cli/runtime/core/plugin | 1,205 | 1,235 | 97.57% |
| **full tree (statements)** | **37,813** | **39,784** | **95.05%** |
| **full tree (branches)** | **9,525** | **11,046** | **86.23%** |

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
