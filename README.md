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

## Local website preview

Run the same pinned Quartz release and site overrides used by GitHub Pages:

```bash
bash scripts/serve_site.sh
```

Then open <http://localhost:8080>. The first run clones Quartz v4.5.2 and installs
its npm dependencies into the ignored `.quartz-local/` cache; later runs reuse it.
Set a different port with `BKC_SITE_PORT=4173 bash scripts/serve_site.sh`. Stop the
server with `Ctrl-C` and rerun the command after editing wiki content. The local
preview skips per-page social-card image generation to keep test builds quick; page
content, navigation, backlinks, and graph behavior match the Pages build.

## How it's maintained

Two layers, clear ownership (see [`AGENTS.md`](AGENTS.md) for the full spec):

| Layer | Who writes it | What |
| --- | --- | --- |
| **Generated** | `scripts/build.mjs` | item stubs, `raw/digest/*`, `sources/_domains.md`, `timeline/_counts.md`, `raw/feed-tags.md` |
| **Synthesis** | the LLM — interactively, *and* daily via `scripts/synthesize_wiki.py` | `topics/`, `people/`, `orgs/`, `events/`, `timeline/<year>.md`, `index.md`, `log.md` |

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

## Berkman Klein Buzz (`archive.json`, daily)

The Buzz newsletter is archived from two sources sharing one id scheme
(`buzz_YYYYMM_N`): 417 issues from the 2006-2015 Sympa-era mailing list
(one-time import), and 426 issues from 2016-present via
**`scripts/fetch_mailchimp_buzz.py`**, synced daily through
`.github/workflows/fetch-mailchimp-buzz.yml`. Filtered strictly to campaigns
internally titled "The Buzz: \<date\>" — the same Mailchimp audience also
sends event announcements and student bulletins, which carry different
privacy/sensitivity expectations and must never end up in this (public)
archive. Full detail (pagination quirks, template-cleaning issues found and
fixed) is in `AGENTS.md` §5. **Known gap:** June 2015–June 2016 isn't
covered by either source.

```bash
export MAILCHIMP_API_KEY=...
python3 scripts/fetch_mailchimp_buzz.py --list-audiences     # find the audience id
python3 scripts/fetch_mailchimp_buzz.py --dry-run --limit 5  # small sanity check
python3 scripts/fetch_mailchimp_buzz.py                      # fetch + merge new issues
```

## BKC publications (`archive.json`, daily)

**`scripts/fetch_publications.py`** syncs BKC's own publications index
(cyber.harvard.edu/publications) into `archive.json` daily, via
`.github/workflows/fetch-publications.yml` — **not SSRN directly**: there's
no single SSRN eJournal for BKC to follow, and SSRN sends explicit
anti-automation signals (`robots.txt` blocks AI crawlers by name, a
Cloudflare bot-challenge, an Elsevier Text-and-Data-Mining opt-out header).
BKC's own page already links out to SSRN/DASH per entry and shows an
abstract, so the wiki still ends up linking to SSRN — just via BKC's own
citation, never by scraping SSRN's site. Already fully backfilled: 374
publications, back to 1993. Daily runs from here are fast (usually 0-1
pages). Full detail (dedup, the DASH-integration follow-up) is in
`AGENTS.md` §5.

```bash
python3 scripts/fetch_publications.py --dry-run --limit 5   # small sanity check
python3 scripts/fetch_publications.py                        # fetch + merge by hand
```

## Automated synthesis (`people/`, `events/`, `orgs/`, `topics/`, daily — currently paused)

Set aside for now (workflow file exists but no `OPENAI_API_KEY` secret is
set, so it's dormant, not removed). **`scripts/synthesize_wiki.py`** turns
whatever the fetch pipelines added overnight into wiki content, via
`.github/workflows/synthesize-wiki.yml` — emphasizing **People and Events as
coherent entities**, so a YouTube video, a
TagTeam bookmark, and a Buzz item that are really about the same person or
real-world occurrence get filed under, and cross-linked from, one page
instead of sitting as disconnected item stubs. Runs on an institutional
OpenAI API key (not Claude Code, which can't use one) via a two-pass design:
plan which entities each new item touches, then draft the actual page
content for each. Scoped to new items only — `raw/.synthesis-state.json`
tracks what's already been considered, and the historical backfill (most
years still "synthesis pending") stays a separate, human-driven effort.
Commits straight to `main` like the fetch pipelines, with guardrails
enforced in code (a hard path allowlist, `--max-items`, `--max-cost-usd`) —
full detail in `AGENTS.md` §5.

```bash
python3 scripts/synthesize_wiki.py --dry-run   # see what it would do, no writes
```

## The Archive API (`api/`)

`api/` is a small **HTTP + MCP service over this wiki**, so `llm_engine` (and any
MCP client) can search, read, and file back into the archive without a local
checkout. It's a separate npm package inside this repo; full detail — endpoints,
production notes, MCP setup — is in [`api/README.md`](api/README.md).

```bash
cd api
npm install
npm run dev                          # dev: tsx watch, http://localhost:4000
curl localhost:4000/v1/health

npm ci && npm run build && npm start # production: node dist/index.js
```

Configure via `api/.env` (copy `api/.env.example`): `PORT`, `ARCHIVE_PATH`
(defaults to this repo root), and `ARCHIVE_API_TOKEN` — **set the token in
production**; when it's unset the API runs unauthenticated. The engine side then
gets `ARCHIVE_API_URL` + the same `ARCHIVE_API_TOKEN`.

Two things to know operationally: the search index is built **at startup**, and
the daily fetch workflows above change content every morning — so a deployment
needs a `git pull` + `POST /v1/reindex` on a cron or its search goes stale
(`api/README.md` → "Keeping content fresh" has the schedule and one caveat: a
deploy script must never `git clean` this checkout, since unreviewed drafts live
in it untracked). And conversations filed by the engine land in
`inbox/conversations/` as **drafts for curator review** — they are not published
pages (the deploy workflow strips `inbox/` and `api/` from the site). See
`AGENTS.md` §5 "Review the inbox".

## Status

Prototype slice = **2025** (737 items). Once you've reviewed the page formats in
Obsidian, the next pass runs `--all` and extends the synthesis layer across all years.
YouTube import, TagTeam sync, and now wiki synthesis itself are all ongoing in the
background (daily, automated).
