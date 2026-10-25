# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## 2.15.1 baseline

| Layer | Hit | Total | Cover | 2.12 target | 2.13 target |
| --- | ---: | ---: | ---: | ---: | ---: |
| api | 2,217 | 2,605 | 85.1% | 75% | 85% |
| jobs | 555 | 610 | 91.0% | 85% | 90% |
| exporters | 1,130 | 1,189 | 95.0% | 90% | 95% |
| mcp | 925 | 1,153 | 80.2% | 80% | 80% |
| steps | 2,089 | 2,662 | 78.5% | — | — |
| application | 6,321 | 7,730 | 81.8% | — | — |
| domain | 1,019 | 1,028 | 99.1% | — | — |
| **full tree** | **15,908** | **19,463** | **81.7%** | — | — |

All four per-layer targets (API 85%, jobs 90%, exporters 95%, MCP 80%)
pass. The enforced release gate (`videoflow.domain`, cache, timeline builder) is
at **98.7%**, above 95%.

## Remaining gap

The full-tree 3.0 gate is still **81.7%**, below 95%. Closing it needs roughly
2,600 more covered statements, concentrated in adapters, step runners, CLI,
services, and external integrations. These need behaviour tests with media,
fakes, or real providers; they are not line-count padding.
