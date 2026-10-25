# Coverage by layer

Measured with:

```bash
uv run coverage run --rcfile=/tmp/coverage.rc -m pytest tests/unit tests/contract -q -o addopts=""
uv run python scripts/coverage_layers.py
```

The `.coveragerc` used for this report disables the release gate's omit list so
adapters, exporters, API, jobs, and MCP are visible.

## 2.14.0 baseline

| Layer | Hit | Total | Cover | 2.12 target | 2.13 target |
| --- | ---: | ---: | ---: | ---: | ---: |
| api | 1,722 | 2,541 | 67.8% | 75% | 85% |
| jobs | 499 | 608 | 82.1% | 85% | 90% |
| exporters | 1,067 | 1,149 | 92.9% | 90% | 95% |
| mcp | 578 | 1,150 | 50.3% | 80% | 80% |
| steps | 2,068 | 2,643 | 78.2% | — | — |
| application | 5,986 | 7,583 | 78.9% | — | — |
| domain | 1,019 | 1,028 | 99.1% | — | — |
| **full tree** | **~9,300** | **12,552** | **~74.5%** | — | — |

The enforced release gate (`videoflow.domain`, cache, timeline builder) is at
**98.5%**, above 95%.

## Gap

The per-layer targets and the 3.0 full-tree 95% gate need roughly 2,100 more
covered statements. Most are adapter/step/route branches that require media,
external providers, or a full job. They need behaviour tests, not assertions on
line counts. This is the remaining coverage work tracked in
[3.0-blockers.md](3.0-blockers.md).
