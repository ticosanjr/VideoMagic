# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## 2.14.1 baseline

| Layer | Hit | Total | Cover | 2.12 target | 2.13 target |
| --- | ---: | ---: | ---: | ---: | ---: |
| api | 2,191 | 2,572 | 85.2% | 75% | 85% |
| jobs | 554 | 610 | 90.8% | 85% | 90% |
| exporters | 1,130 | 1,189 | 95.0% | 90% | 95% |
| mcp | 923 | 1,150 | 80.3% | 80% | 80% |
| steps | 2,070 | 2,643 | 78.3% | — | — |
| application | 6,229 | 7,628 | 81.7% | — | — |
| domain | 1,019 | 1,028 | 99.1% | — | — |
| **full tree** | **15,752** | **19,292** | **81.7%** | — | — |

All four per-layer targets (API 85%, jobs 90%, exporters 95%, MCP 80%)
now pass. The enforced release gate (`videoflow.domain`, cache, timeline
builder) is at **98.7%**, above 95%.

## Remaining gap

The full-tree 3.0 gate is still **81.7%**, below 95%. Closing it needs roughly
2,600 more covered statements, concentrated in adapters, step runners, CLI,
services, and external integrations. These need behaviour tests with media,
fakes, or real providers; they are not line-count padding.
