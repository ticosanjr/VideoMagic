# Alpha matrix

| Use | Format | Codec / pix_fmt |
| --- | --- | --- |
| Transparent graphic intermediate | `.mov` | `prores_ks`, `yuva444p10le` |
| Lightweight transparent web graphic | `.webm` | `libvpx-vp9`, `yuva420p`, `-auto-alt-ref 0` |
| Still overlay | `.png` | RGBA |
| Opaque B-roll / PiP source | `.mp4` | `yuv420p` |

An overlay used as a matte must carry alpha. `yuv420p` or `rgb24` mattes fail
with `alpha_channel_missing`.

`vf_pip` uses a cached rounded PNG mask and `yuva420p`; `vf_parallax` renders
background and subject into one opaque graphic.
