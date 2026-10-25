# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## 2.17.1 baseline

| Layer | Hit | Total | Cover | 2.12 target | 2.13 target |
| --- | ---: | ---: | ---: | ---: | ---: |
| api | 2,222 | 2,610 | 85.1% | 75% | 85% |
| jobs | 554 | 610 | 90.8% | 85% | 90% |
| exporters | 1,130 | 1,189 | 95.0% | 90% | 95% |
| mcp | 932 | 1,161 | 80.3% | 80% | 80% |
| steps | 2,198 | 2,786 | 78.9% | — | — |
| application | 6,323 | 7,730 | 81.8% | — | — |
| domain | 1,019 | 1,028 | 99.1% | — | — |
| **full tree** | **16,038** | **19,610** | **81.8%** | — | — |

All four per-layer targets pass. The enforced release gate
(`videoflow.domain`, cache, timeline builder) is at **98.7%**.

## Remaining gap

The full-tree 3.0 gate is still **81.8%**, below 95%. Closing it needs roughly
2,500 more covered statements, concentrated in adapters, step runners, CLI,
services, and external integrations.
