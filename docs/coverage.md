# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## Current working tree (3.2.1)

Measured with the release-gate omit list disabled. The full unit/contract run is
**2,660 passed, 2 skipped, 1 xfailed**.

| Layer | Hit | Total | Cover |
| --- | ---: | ---: | ---: |
| api | 3,065 | 3,175 | 96.54% |
| jobs | 700 | 766 | 91.38% |
| exporters | 1,712 | 1,796 | 95.32% |
| mcp | 1,150 | 1,234 | 93.19% |
| steps | 9,987 | 10,475 | 95.34% |
| application | 19,401 | 20,574 | 94.30% |
| domain | 1,640 | 1,660 | 98.80% |
| **full tree (statements)** | **41,002** | **43,160** | **95.00%** |
| **full tree (branches)** | **10,340** | **11,988** | **86.25%** |

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
