# Upscale

`mcp-vf-vision-fx.upscale_media` upscales images and videos with a deterministic
backend chain. The default is `auto`.

## Backends

| Backend | When used | Notes |
| --- | --- | --- |
| `remote` | `ComputeRouter` reports `upscale` healthy | Uses the GPU worker; output name follows the source extension |
| `realesrgan_cmd` | `VF_REALESRGAN_CMD` is set | Custom command with `{input}`, `{output}`, `{scale}` |
| `realesrgan` | `realesrgan-ncnn-vulkan` is on `PATH` | Images directly; videos via frame extraction |
| `ffmpeg` | fallback | Lanczos scale, preserves audio and adds `+faststart` |

Pass `backend="remote"`, `"realesrgan"`, `"realesrgan_cmd"` or `"ffmpeg"` to
force one. If it is unavailable, the tool falls back and reports why.

## Video with Real-ESRGAN

An ncnn Vulkan build usually accepts image files or a directory of frames, not
a video container. Video upscale therefore:

1. extracts every frame with FFmpeg;
2. upscales the frame directory with Real-ESRGAN;
3. re-encodes with the original frame rate;
4. maps the original audio back with `-map 1:a?`;
5. writes H.264/AAC with `+faststart`.

This can be slow for long media. The GPU worker path is preferred when
available.

## Custom command

```bash
export VF_REALESRGAN_CMD='realesrgan-ncnn-vulkan -i {input} -o {output} -s {scale}'
```

A custom command is responsible for video support. If it cannot process video,
use `backend="realesrgan"` or `ffmpeg` instead.

## Limits and cache

- `scale` is an integer from 1 to 8.
- Output above `8192px` on either side is rejected.
- The cache key includes the source fingerprint, scale, video/image flag, and
  concrete backend. A Lanczos fallback cannot hide a later Real-ESRGAN result.
- The sidecar records `backend`, `fallback`, `fallback_reason`, `dimensions`,
  and `scale`.
