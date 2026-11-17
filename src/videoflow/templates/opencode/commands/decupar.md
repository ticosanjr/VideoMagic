---
description: Ingest a source and prepare the deterministic base timeline.
agent: build
---

# /decupar

Use VideoFlow MCP tools only.

1. Ask which style from `./presets/*.md` to use and bind it with
   `vf_project(action="init|open", style_id=...)`.
2. Run `vf_ingest(action="session")` with the provided source or `raw_dir`.
3. Transcribe with `transcribe_word_aligned`; run `session.cull` if retakes exist.
4. Return project state, transcript summary and artifacts.
