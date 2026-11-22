> Histórico: o script `scripts/shorts_benchmark.py` foi removido na v4.2. Use `scripts/e2e_micro_gate.py` e os testes de Shorts.

# Scene intelligence and Dynamic Shorts benchmark

The phase 7 harness is deterministic and produces JSON and Markdown evidence.

```bash
uv run python scripts/shorts_benchmark.py --full
```

Evidence:

```text
docs/qa-evidence/shorts-benchmark.json
docs/qa-evidence/shorts-benchmark.md
```

## What it checks

- Scene-boundary F1 on a 10-minute synthetic corpus with known cuts.
- Scene detection throughput extrapolated to one hour.
- Face crop horizontal error for left/right 60 s sequences.
- `FULL_FACE -> SPLIT_BROLL -> SPLIT_SCREEN_SAFE` plan composition.
- Caption grouping, 18-character lines, two-line limit, zero overlaps.
- Last-two-seconds caption coverage, 350 ms end padding, 80 ms fade.
- Shorts safe-zone dimensions (380 px bottom, 140 px right).

## Performance split

The 45 s/h acceptance target applies to the **scene-detection pass** (proxy
plus PySceneDetect). Initialization, face metrics, and keyframes are reported
separately as `full_pipeline_sec_per_hour` so the release never hides the cost
of enrichment.

Keyframes are extracted in a single batched decode pass; visual sampling is
parallelised across scenes. Detection uses frame skipping proportional to the
source FPS to keep the pass under the target without losing 10-minute corpus
cuts.

## Pending physical certification

`render_60s_sec` remains `null` until a Windows RTX 3060 worker measurement is
recorded. The harness reports `pending_physical_worker` and never claims a GPU
speedup from local CI.

The synthetic corpus is not a substitute for an annotated production corpus.
Replace `--video`/`--cut-every` before claiming production F1.
