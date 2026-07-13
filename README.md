# BKC Archive Wiki

An LLM-maintained wiki over the **Berkman Klein Center** curated link feed
(Harvard TagTeam hub 1176) — originally **6,925 bookmarks**, 2014–2026, across
~2,000 sources on internet/tech/society/law/AI/policy, now growing daily via
an automated sync (see below).

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

## YouTube transcripts (`collection/` → `archive.json`)

A separate, additive **source layer** lives in `collection/` — full transcripts
and metadata for every video on the **@BKCHarvard** channel (`json/youtube.json`
catalog + one `txt/youtube/yt_<id>.txt` per video), ready for the `llm_engine`
RAG ingestion framework. Two fetch mechanisms write into it:

- **`scripts/fetch_youtube_api.py`** — the official YouTube Data API v3,
  OAuth-authenticated as a BKCHarvard channel manager. This is the
  ToS-compliant path, and it's what runs **automatically every day** via
  `.github/workflows/fetch-youtube-captions.yml`, budgeted to stay under the
  free API quota (~40 videos/day).
- **`scripts/fetch_youtube.py`** — an unofficial scraper (Innertube +
  `youtube-transcript-api`), kept as a faster manual/local fallback but not
  used by the daily automation.

Every daily run also folds newly-fetched videos into `raw/archive.json` via
**`scripts/merge_youtube_into_archive.py`** (lightweight entries only — the
full transcript text stays in its own `.txt` file, referenced by
`transcript.path`, rather than bloating the shared `archive.json`). That's
what makes YouTube videos show up as regular item stubs the next time
`build.mjs` runs. Full operational detail — quota math, OAuth setup, the
scraper's proxy/cooldown behavior — is in `AGENTS.md` §5.

```bash
python3 scripts/fetch_youtube_api.py --dry-run      # see what's new (no writes)
python3 scripts/merge_youtube_into_archive.py       # fold fetched videos into archive.json by hand
```

## TagTeam items (`archive.json`, daily)

Beyond the original 6,925-item export, **`scripts/fetch_tagteam.py`** syncs
new items from hub 1176 straight into `archive.json` every day, via
`.github/workflows/fetch-tagteam-items.yml` — no credentials needed, since
the hub's `items.json`/`items.rss` are its own public "Export" feature.
Incremental: pages through newest-first and stops once a full page has
nothing new, so it never re-walks the full history. Full detail (including a
known edge case around backdated tags) is in `AGENTS.md` §5.

```bash
python3 scripts/fetch_tagteam.py --dry-run   # see what's new (no writes)
python3 scripts/fetch_tagteam.py             # fetch + merge by hand
```

## Status

Prototype slice = **2025** (737 items). Once you've reviewed the page formats in
Obsidian, the next pass runs `--all` and extends the synthesis layer across all years.
Both YouTube import and TagTeam sync are ongoing in the background (daily, automated)
— re-run `build.mjs --all` periodically to pick up newly-merged items.
