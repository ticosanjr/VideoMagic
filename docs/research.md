# Research and script providers

The Full AI Editor research phase is local-first and citation-aware.

## Providers

| Provider | Network | Cost | Notes |
| --- | --- | --- | --- |
| `local` | no | free | Search Markdown, text, HTML, JSON, CSV, and SRT in `search.local_paths` |
| `crawl` | yes | free | Fetch configured seed URLs and search their text |
| `searxng` | optional local | free/open-source | JSON API from a self-hosted or configured SearXNG |
| `wikipedia` | yes | free | MediaWiki search API, language configurable |
| `internet_archive` | yes | free | `advancedsearch.php` metadata results |
| `duckduckgo` | not enabled | free | Reserved; scraping is rate-limited and not part of the default chain |

The default chain is `local`. External providers require
`allow_external_services=true` on the step or `VIDEOWFLOW_ALLOW_EXTERNAL` to be
enabled. Fetches reject private/loopback hosts, honour `robots.txt`, cap size,
and cache text under `search-cache/`.

## Steps

| Step | Output |
| --- | --- |
| `research.multi_agent` | `research/agent_*.json` and `.md`, one dossier per scope |
| `research.consolidate` | `research/master.json` and `master.md`, deduplicated |
| `presenter.profile` | `research/presenter-profile.json` and `.md` |
| `script.dual_output` | `script/narration.txt`, `edition.md`, `script.json` |

Research sources are untrusted data. Prompts explicitly separate instructions
from source text. A model may only cite URLs present in the manifest; unknown
URLs are marked `verified: false` for human review. If no LLM is configured, the
steps still write a source digest and a template script so the HILT review gates
can be used.

## Full AI Editor sequence

```
brief (human.input)
  → research.multi_agent
  → research_files (human.files, optional corrections)
  → research_review (human.gate)
  → research.consolidate
  → research_master_review (human.gate)
  → script.dual_output
  → script_files (human.files, optional corrections)
  → script_review (human.gate)
  → ingest / VAD / transcribe / ...
```

## Settings

`settings.search.providers`, `local_paths`, `seed_urls`, `searxng_url`,
`wikipedia_language`, `max_results`, `fetch_pages`, `allow_network`,
`cache_ttl_hours`. All are editable in Settings → Research providers.
