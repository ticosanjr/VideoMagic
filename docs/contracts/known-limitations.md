# Known limitations

- Remote Windows GPU is optional. When it is offline, jobs run locally and are
  marked `degraded: true` with a reason.
- The GPU worker must be paired through `gpu.json`. Do not rely on a frozen
  `VF_GPU_WORKER_URL` in `opencode.json`.
- Stock providers without API keys use keyless fallbacks; licensing and
  attribution still need review.
- Semantic retake cleanup without a configured LLM is delegated to OpenCode via
  `semantic_candidates`; it is not applied automatically.
- SMB shared mounts are an accelerator. A failed shared write falls back to
  HTTP automatically.
- Full physical certification on Windows/NVIDIA hardware is pending.
