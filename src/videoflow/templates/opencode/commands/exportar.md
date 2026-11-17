---
description: Export the master bundle to MP4, Resolve, Premiere and Kdenlive.
agent: build
---

# /exportar

1. Confirm the timeline revision and selected style.
2. Run `vf_exports(action="bundle", project_id=..., targets="all")`.
3. If validation fails, report missing media, duration mismatch or blocked
   licenses before retrying.
4. Return the bundle manifest path and the four artifacts.
