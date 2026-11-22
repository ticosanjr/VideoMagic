# Decupage benchmark

The benchmark harness validates the deterministic part of the decupage engine
before physical GPU certification.

## Self-test

> Histórico: o script `scripts/decupage_benchmark.py` foi removido na v4.2.
> O comportamento determinístico agora é coberto pelos testes abaixo.

```bash
uv run pytest tests/unit/test_decupage_snap.py tests/unit/test_decupage_review.py -q
```

Current evidence: **synthetic passed**, physical acceptance pending.

Measured:

- retake recall;
- noise recall;
- false-positive ratio;
- frame quantisation;
- active/cut counts;
- deterministic runtime.

Pending physical metrics:

- clipped syllables (requires real audio + forced-alignment audit);
- audio clicks/pops (requires rendered audio analysis);
- A/V drift over one hour.

## Golden video

A real 15-minute golden recording must include:

1. three takes of the same sentence (incomplete, complete with a stutter, clean);
2. three isolated coughs, two throat clears, and one microphone tap;
3. 20 cuts starting on plosives and ending on sibilants;
4. one retake crossing a 4-minute window boundary;
5. import validation in DaVinci Resolve.

Pass `--manifest` with the schema used by `self_test_manifest()` and
`golden_video: true`. The harness keeps `physical_acceptance_pending` true
until that manifest is supplied.

Thresholds:

| Metric | Target |
| --- | ---: |
| Retake recall | ≥95% |
| Noise recall | ≥92% |
| False positives | ≤1% of useful time |
| Clipped syllables | 0 |
| Audio clicks | 0 |
| A/V drift | ≤1 frame/hour |

## Gate

`./scripts/gate_mcp.sh` keeps the MCP coverage floor at 80%. The benchmark test
is included in the MCP-focused suite; the full physical corpus remains a manual
hardware gate.
