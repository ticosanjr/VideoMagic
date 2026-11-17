---
name: video-clone-style
description: Extract, save, and apply a new channel style from a reference.
---

# Clone style workflow

1. Ask for the reference URL, folder of prints, or manual direction.
2. Call `vf_project(action="clone_style", ...)` or `vf_style(action="save")`
   with the canonical Markdown frontmatter.
3. Sync to the workspace with `vf_style(action="sync", workspace_dir=...)`.
4. Show the new `presets/<style_id>.md` and ask for approval.
5. Bind the style with `vf_project(action="init|open", style_id=...)`.
