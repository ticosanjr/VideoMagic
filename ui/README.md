# VideoFlow UI

SvelteKit 2 + Svelte 5 + Tailwind CSS 4 rack scaffold.

```bash
npm install
npm run dev      # http://127.0.0.1:5173
npm run check
npm run build
```

The dev server proxies `/api` and `/mcp` to `http://127.0.0.1:8765`.

This is a static shell. The cards render the eight modules with sample state; no
API call is made yet. The live behavior is specified in
[../docs/ui-spec.md](../docs/ui-spec.md). English strings only.

Do not add pipeline logic here. The UI edits decisions; the API computes them.
