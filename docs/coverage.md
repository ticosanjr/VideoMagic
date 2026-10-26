# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## 2.20.0 baseline

| Layer | Hit | Total | Cover | 2.12 target | 2.13 target |
| --- | ---: | ---: | ---: | ---: | ---: |
| api | 2,280 | 2,681 | 85.0% | 75% | 85% |
| jobs | 554 | 610 | 90.8% | 85% | 90% |
| exporters | 1,130 | 1,189 | 95.0% | 90% | 95% |
| mcp | 932 | 1,161 | 80.3% | 80% | 80% |
| steps | 2,218 | 2,807 | 79.0% | — | — |
| application | 6,552 | 7,977 | 82.1% | — | — |
| domain | 1,019 | 1,028 | 99.1% | — | — |
| **full tree** | **16,434** | **20,059** | **81.9%** | — | — |

All four per-layer targets pass. The full-tree 95% gate remains open.
