# Settings

`settings.json` under the VideoFlow home stores the local configuration. The
Settings tab adds search, units, help tips, and a discard-changes action.

| Section | Fields | Notes |
| --- | --- | --- |
| Runtime | host, port, log level, locale, max jobs, history, open browser | Host/port changes need a service restart |
| Paths | allowed roots, FFmpeg/FFprobe, cache, models, output, temp | Allowed roots gate every file access |
| Models | default per capability, device, compute type, threads, HF token env | Empty default lets the engine pick |
| Automation and quality | scheduler interval, retries, backoff, target LUFS, true peak, VMAF, proxy height | Quality values feed audio/visual QA |
| LLM and speech | temperature, timeout, max tokens, retries, JSON mode, ASR engine/language/device | Copilot and transcript features |
| TTS, stock, translation, UI | TTS voice/model, stock provider, translation, theme, density, locale | Theme/density are shell-only |

Search filters sections by their visible text. `Discard changes` reloads the
saved file without touching the server. `Reset` restores server defaults and
asks for confirmation.
