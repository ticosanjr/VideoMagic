# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## Current working tree (2.72.4)

Measured after the notification reduction work, with the release-gate omit list
disabled. The full unit/contract run is **2,160 passed, 1 skipped, 1 xfailed**.

| Layer | Hit | Total | Cover |
| --- | ---: | ---: | ---: |
| api | 2,844 | 2,944 | 96.60% |
| adapters | 1,330 | 1,375 | 96.73% |
| application | 15,335 | 16,285 | 94.17% |
| engine | 1,090 | 1,157 | 94.21% |
| exporters | 1,211 | 1,261 | 96.03% |
| mcp | 991 | 1,021 | 97.06% |
| steps | 7,629 | 8,071 | 94.52% |
| domain | 1,175 | 1,181 | 99.49% |
| cli/runtime/core/plugin | 1,109 | 1,139 | 97.37% |
| **full tree (statements)** | **32,748** | **34,471** | **95.00%** |
| **full tree (branch report)** | — | — | **88.1%** |

The full-tree 95% target remains **met**. The configured release gate remains at
98% on its selected source set, which is narrower than this report. The
remaining misses are concentrated in defensive branches for optional backends,
offline paths, and platform-specific tray/notifier code.

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
