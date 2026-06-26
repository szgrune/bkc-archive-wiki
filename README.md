# BKC Archive Wiki

An LLM-maintained wiki over the **Berkman Klein Center** curated link feed
(Harvard TagTeam hub 1176) — **6,925 bookmarks**, 2014–2026, across ~2,000 sources
on internet/tech/society/law/AI/policy.

It follows the **LLM Wiki** pattern: an immutable source
(`raw/archive.json`) sits underneath a persistent, interlinked set of markdown pages
that an LLM writes and keeps current. You curate and ask questions; the LLM does the
summarizing, cross-referencing, and filing.

## How to browse it

Open this folder (`archive-wiki/`) as an **Obsidian vault**. Then:

- **Start at [`index.md`](index.md)** — the catalog of everything, by category.
- **Topic pages** (`topics/`) are the heart of it — LLM-derived subjects, since the
  feed's own tags (`community`, `orbit`, `buzz`…) are newsletter sections, not topics.
- **Item pages** (`items/<year>/`) are one-per-bookmark stubs. They look sparse on
  their own — the value is in their **Backlinks pane**, which shows every topic,
  person, and org that references them.
- **Graph view** shows the shape: topic/person/org pages are hubs; items are leaves.
- **Timeline** (`timeline/`) reads the archive year by year.

## How it's maintained

Two layers, clear ownership (see [`AGENTS.md`](AGENTS.md) for the full spec):

| Layer | Who writes it | What |
| --- | --- | --- |
| **Generated** | `scripts/build.mjs` | item stubs, `raw/digest/*`, `sources/_domains.md`, `timeline/_counts.md`, `raw/feed-tags.md` |
| **Synthesis** | the LLM | `topics/`, `people/`, `orgs/`, `timeline/<year>.md`, `index.md`, `log.md` |

Regenerate the generated layer any time (idempotent):

```bash
node scripts/build.mjs --year=2025   # one year of stubs (default)
node scripts/build.mjs --all         # all 6,925 items
```

Then ask the LLM to ingest / synthesize / query / lint — those workflows are
defined in `AGENTS.md`. Everything is plain markdown in git, so you get version
history for free.

## YouTube transcripts (`collection/`)

A separate, additive **source layer** lives in `collection/` — full transcripts
and metadata for every video on the **@BKCHarvard** channel, scraped by
`scripts/fetch_youtube.py` into a RAG-ready shape (`json/youtube.json` catalog +
one `txt/youtube/yt_<id>.txt` per video). Unlike the metadata-only TagTeam corpus,
this layer carries real body text, ready for the `llm_engine` RAG ingestion
framework. It never modifies `archive.json`.

```bash
pip install youtube-transcript-api requests
python3 scripts/fetch_youtube.py            # resumable; see AGENTS.md for proxy setup
```

YouTube rate-limits bulk transcript fetching, so the run is resumable and supports
rotating proxies (`YT_PROXY_FILE`). Full operational detail — including the
Webshare proxy workflow and the block/cooldown behavior — is in `AGENTS.md` §5.

## Status

Prototype slice = **2025** (737 items). Once you've reviewed the page formats in
Obsidian, the next pass runs `--all` and extends the synthesis layer across all years.
