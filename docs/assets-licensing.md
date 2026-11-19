# Art direction, assets, and licensing

## Art direction

`style.guide` extracts a palette from approved reference images with FFmpeg and
merges the editorial direction. It writes `style/style-guide.json` and `.md`
with palette, typography, texture, motion, audio, and rules. The HILT
`style_review` gate locks it before asset discovery.

`storyboard.units` turns `script/script.json` into timed units with layout
placeholders (`lower_third`, `full_screen`, `presenter_split`,
`presenter_visual`) and an asset query per unit.

## Providers

| Provider | Media | License status |
| --- | --- | --- |
| Pexels | video, image | `cleared` |
| Pixabay | video, image | `cleared` |
| Openverse | image, audio | `cleared` / `cc_review` |
| Wikimedia Commons | image, video | `cleared` / `cc_review` |
| Internet Archive | video, image | `cleared` / `cc_review` / `unknown` |
| YouTube (`yt-dlp`) | short video excerpt | `fair_use_review` |

YouTube is intentionally limited to short excerpts:

- `stock.youtube_fair_use_seconds` (default 15s);
- `stock.youtube_max_per_video` (default 3);
- the CLI records clip start/end and a fair-use rationale;
- the asset remains `fair_use_review` until a human approves the license gate.

Every candidate records provider, page URL, download URL, creator, license,
license URL, status, commercial allowance, attribution requirement, clip bounds,
retrieved timestamp, and SHA-256 after download.

## Ledger and export

`assets.harvest` and `assets.license_audit` write:

- `assets/manifest.json` — downloaded assets and warnings;
- `assets/licenses.json` — the ledger;
- `assets/licenses.md` — a readable review sheet.

The final `export.nle` has `require_licenses: true`. It raises an export error
while an asset **used by the timeline, overlays, B-roll plan, or audio plan** is
`unknown`/`cc_review`/`quarantined` without approval or is `fair_use_review`
without approval. Unused ledger entries no longer block delivery. With a project
state available, the gate is scoped automatically; pass no state to audit the
whole ledger. The HILT `assets_review` gate is the approval point;
`assets.assign` records the approval and writes `assets/assignments.json` plus
`broll.json`.

Use `vf_assets(action="list")` to inspect the scoped ledger and
`vf_assets(action="approve"|"quarantine")` to record a decision without
re-running discovery. Approved records store the license and attribution text;
quarantined records stay blocked until reviewed again.

`assets.assign` places approved assets on the B-roll plan with start/duration,
license status, attribution, and source URL. The NLE sidecars include
`licenses.json`, `licenses.md`, and `assignments.json`.

## Settings

- `stock.pexels_key_env` (default `PEXELS_API_KEY`);
- `stock.pixabay_key_env` (default `PIXABAY_API_KEY`);
- `stock.openverse_token_env` (default `OPENVERSE_TOKEN`);
- `stock.youtube_fair_use_seconds`;
- `stock.youtube_max_per_video`;
- `stock.allow_fair_use`.

No paid provider is required. Missing keys simply remove that provider from the
available chain.

## Expiry

`AssetCandidate.expires_at` is carried through the ledger. An asset whose
`expires_at` is in the past is a blocker even when its license status is
`cleared` or it was manually approved. `assets.license_audit`, `assets.review`,
and `export.nle` therefore stop on expired clearances until the ledger is
refreshed.
