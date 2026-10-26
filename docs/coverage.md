# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## 2.19.0 baseline

| Layer | Hit | Total | Cover | 2.12 target | 2.13 target |
| --- | ---: | ---: | ---: | ---: | ---: |
| api | 2,244 | 2,640 | 85.0% | 75% | 85% |
| jobs | 554 | 610 | 90.8% | 85% | 90% |
| exporters | 1,130 | 1,189 | 95.0% | 90% | 95% |
| mcp | 932 | 1,161 | 80.3% | 80% | 80% |
| steps | 2,211 | 2,805 | 78.8% | — | — |
| application | 6,412 | 7,826 | 81.9% | — | — |
| domain | 1,019 | 1,028 | 99.1% | — | — |
| **full tree** | **16,233** | **19,837** | **81.8%** | — | — |

All four per-layer targets pass. The enforced release gate is at **98.7%**.

## Remaining gap

The full-tree 3.0 gate is still **81.8%**, below 95%. Closing it needs roughly
2,600 more covered statements in adapters, step runners, CLI, services, and
external integrations.
