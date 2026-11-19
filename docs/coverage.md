# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## Current working tree (3.4.0 development)

Measured with the release-gate omit list disabled. The full unit/contract run is
**2,828 passed, 2 skipped, 1 xfailed**.

| Layer | Hit | Total | Cover |
| --- | ---: | ---: | ---: |
| api | 3,218 | 3,335 | 96.49% |
| jobs | 705 | 789 | 89.35% |
| exporters | 1,752 | 1,837 | 95.37% |
| mcp | 1,242 | 1,364 | 91.06% |
| steps | 10,130 | 10,619 | 95.40% |
| application | 20,638 | 21,850 | 94.45% |
| domain | 1,643 | 1,663 | 98.80% |
| **full tree (statements)** | **42,727** | **44,963** | **95.03%** |
| **full tree (branches)** | **10,839** | **12,550** | **86.37%** |

The hybrid compute router and worker status add unit coverage without lowering
the full-tree target. Remaining misses are optional CUDA backends, offline
providers, and platform-specific tray/notifier paths.

## 3.3.0 release

Measured with the release-gate omit list disabled. The full unit/contract run is
**2,788 passed, 2 skipped, 1 xfailed**.

| Layer | Hit | Total | Cover |
| --- | ---: | ---: | ---: |
| api | 3,065 | 3,175 | 96.54% |
| jobs | 703 | 784 | 89.67% |
| exporters | 1,752 | 1,837 | 95.37% |
| mcp | 1,240 | 1,362 | 91.04% |
| steps | 10,130 | 10,619 | 95.40% |
| application | 20,467 | 21,669 | 94.45% |
| domain | 1,643 | 1,663 | 98.80% |
| **full tree (statements)** | **42,386** | **44,600** | **95.04%** |
| **full tree (branches)** | **10,803** | **12,502** | **86.41%** |

The 3.3.0 compositors, QA modes, licensing scope, and project-slug paths keep the
full-tree statement target met. Remaining misses are defensive branches for
optional backends, offline providers, and platform-specific tray/notifier code.

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
