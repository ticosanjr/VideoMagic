# videoflow-mcp-vision

Isolated stdio MCP server with the VideoFlow 2.90 vision tools. Assets, license
sidecars, and cache keys come from `vf-contracts`; remote jobs go through
`vf-compute` with local FFmpeg or CLI fallbacks.

## Tools

| Tool | Output |
| --- | --- |
| `transcribe_word_aligned` | `captions/transcript.json`, `captions.srt`, `captions.ass` |
| `remove_background` | `assets/matte/*` |
| `upscale_media` | `assets/upscaled/*` |
| `render_motion_graphic` | `assets/graphics/*.mp4` |
| `image_to_broll_motion` | `assets/broll/*.mp4` |

## Environment

- `VF_WORKSPACE_ROOT` — shared 2.90 workspace, matching `vf-contracts`.
- `VF_PROJECTS_ROOT` / `VF_PROJECT_OUTPUT` — fallback project resolution.
- `VF_WHISPER_BIN`, `VF_WHISPER_MODEL` — local whisper.cpp transcription.
- `VF_REMBG_CMD` — optional rembg command template.
- `VF_REALESRGAN_CMD` — optional Real-ESRGAN command template.
- `VF_REMOTION_CMD`, `VF_MANIM_CMD` — motion-graphics command templates.
- `VF_FFMPEG` — FFmpeg executable override.
- `VF_BROLL_SIZE` — output size for image B-roll, default `1080x1920`.

Templates are split with `shlex` and expanded into an argv list; the tools never
invoke a shell. Placeholders are `{input}`, `{output}`, `{entry}`, `{code}`,
`{props}`, `{duration}`, `{engine}`, and `{scale}`.

## Run

```bash
videoflow-mcp-vision
```
