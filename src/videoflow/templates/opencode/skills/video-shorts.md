---
name: video-shorts
description: Produce 9:16 Shorts/Reels with the selected channel style.
---

# Shorts workflow

1. Confirm the style in `presets/*.md`; never assume one.
2. Use `shorts`/`vf_exec(action="short")` for selection and render.
3. Keep captions, safe zones and cut rhythm from the style.
4. Run `vf_qa(action="inspect")` before presenting.
5. Export the short and the master bundle; record review rules with
   `vf_style(action="learn_rule")`.
