# videoflow-mcp-audio

Isolated stdio MCP server with the VideoFlow 2.90 audio tools. It shares asset
sidecars and cache keys through `vf-contracts` and remote compute through
`vf-compute`, with a local FFmpeg fallback whenever a remote capability is not
healthy.

## Tools

| Tool | Output |
| --- | --- |
| `tts_generate` | `assets/audio/*.wav` |
| `voice_clean_and_enhance` | `assets/audio/*_clean.wav` |
| `separate_audio_stems` | `assets/stems/*` |
| `generate_music_or_sfx` | `assets/audio/*.wav` |
| `mix_and_master_track` | `assets/audio/master.wav` |

## Environment

- `VF_WORKSPACE_ROOT` — shared 2.90 workspace, matching `vf-contracts`.
- `VF_PROJECTS_ROOT` / `VF_PROJECT_OUTPUT` — fallback project resolution.
- `VF_POCKET_TTS_CMD`, `VF_PIPER_CMD` — local TTS command templates.
- `VF_DEEPFILTER_CMD` — optional DeepFilterNet command template.
- `VF_AUDIO_SEPARATOR_CMD` — optional stem separator command template.
- `VF_FFMPEG` — FFmpeg executable override.

Templates are split with `shlex` and expanded into an argv list; the tools never
invoke a shell. Placeholders are `{input}`, `{output}`, `{text}`, `{voice}`,
`{voice_ref}`, `{language}`, `{stems}`, `{output_dir}`, and `{scale}`.

## Run

```bash
videoflow-mcp-audio
```
