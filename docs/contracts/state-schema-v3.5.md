# State schema v3.5

## Sources

`state.sources` maps `source_id` to media info. `state.primary_source_id` is a
default, not the only source. `VideoSegment` and `AudioSegment` carry
`source_id`; the time map converts source time to timeline time.

## Transcript

- `state.transcript`: raw sentences with word timings.
- `state.transcript_clean`: sentences after editorial cleanup.
- `state.pipeline.discard_sentence_ids`: authoritative removal list.

Word timestamps are sample-based and nested under each sentence.

## Execution

Every routed job carries:

```json
{
  "execution_node": "remote_gpu:worker",
  "device": "remote_gpu",
  "degraded": false,
  "degraded_reason": "",
  "elapsed_sec": 12.3,
  "started_at": "2026-11-19T...",
  "finished_at": "2026-11-19T..."
}
```

## QA

Every artifact report includes `run_id`, `artifact_path`,
`artifact_sha256`, `status`, `metrics`, `issues`, and `degraded`.
