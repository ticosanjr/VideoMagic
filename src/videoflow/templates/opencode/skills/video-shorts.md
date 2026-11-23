---
name: video-shorts
description: Produce 9:16 Shorts/Reels with the selected channel style.
---

# Shorts workflow

1. Confirm the style in `presets/*.md`; never assume one.
2. Use `vf_decupage`/`vf_timeline` for selection and `vf_shorts` for render.
3. Keep captions, safe zones and cut rhythm from the style.
4. Run `vf_jobs(action="qa")` before presenting.
5. Export the short and the master bundle; record review rules with
   `vf_style(action="learn_rule")`.
