# BKC Archive Wiki — operating manual

This file tells an LLM agent (Claude Code, Codex, etc.) how this wiki is
structured and how to maintain it. It is the **key config**. Read it first every
session. Co-evolve it as conventions improve.

This is an instance of the **LLM Wiki** pattern: a persistent, interlinked
markdown knowledge base that the LLM builds and maintains on top of an immutable
source. The human curates and asks questions; the LLM does the bookkeeping.

---

## 1. What the corpus is

`raw/archive.json` is the **primary source** — a merged dataset of:

- **TagTeam hub 1176** — BKC's own curated link feed
  (tagteam.harvard.edu/hubs/1176), synced daily. Each item is a bookmark:
  `id` (numeric), `title`, `url`, `date_published`, `tags`, sometimes a short
  HTML `description`, almost never full `content`. Originally **6,925 items**
  (2014–2026, bulk 2017+) from a one-time export; `scripts/fetch_tagteam.py`
  now adds new ones daily (see §5). **2,063 unique domains** (NYT, Wired,
  techpolicy.press, SSRN, Harvard, 404media…). Subject matter:
  internet/tech/society/law/AI/policy.
- **Berkman Buzz newsletters** — 417 email issues, **2006–2015**. Weekly digests
  from the Center. Item IDs: `buzz_YYYYMM_N`. Full body text in `content` field;
  `email` sub-object carries message-id, list, source-file.
- **BKC YouTube videos** — @BKCHarvard channel (~1,100 videos; import ongoing,
  daily). Item IDs: `yt_VIDEO_ID`. `youtube` sub-object carries duration,
  speakers, caption type. `content` here is the video description, not the
  transcript — the full transcript stays out of `archive.json` (see §2) and
  lives at the path in `transcript.path`.
- **BKC publications** — from BKC's own curated index at
  cyber.harvard.edu/publications (NOT scraped from SSRN — see §5 for why),
  synced daily via `scripts/fetch_publications.py`. Item IDs:
  `pub_<year>-<slug>` derived from BKC's own URL. `content` is the full
  abstract (BKC's own published summary). `publication` sub-object carries
  `topics` (BKC's own categorization), `external_links` (`{"ssrn": url,
  "dash": url}` — wherever BKC's page itself links out to), and
  `authors_profiles` (`[{name, bkc_profile_url}]` — useful for cross-
  referencing existing `people/*.md` pages during synthesis).

**Total: 7,390+ items** (and climbing daily — see §5).

### Two constraints that shape everything
1. **Metadata-only for TagTeam items.** There is no article body text. Do **not**
   fetch URLs during normal ingest/synthesis. Topics are derived from titles, domains
   and short descriptions. (On-demand fetching of a *specific* item is fine when asked
   — note it in the log.) Buzz items carry full `content` inline. YouTube items carry
   only the video description inline — the transcript lives in its own file under
   `collection/txt/youtube/`, pointed to by `transcript.path` (see §2).
2. **The feed tags are NOT topical.** `community`, `orbit`, `buzz`, `events`,
   `opportunities` are BKC newsletter-section/workflow tags (plus housekeeping like
   `added`, `skip`). They tell you the *channel*, not the *subject*. All topical
   structure is **LLM-derived** and lives in `topics/`. See `raw/feed-tags.md`.

---

## 2. Layout & ownership

```
archive-wiki/
├── AGENTS.md          this file
├── README.md          human orientation                            [LLM]
├── index.md           catalog of the wiki, by category              [LLM]
├── log.md             append-only chronological record              [LLM]
├── items/<year>/<id>-<slug>.md   one stub per item                  [SCRIPT]
├── topics/<slug>.md   topical/theme pages — the value layer         [LLM]
├── people/<slug>.md   recurring authors / named individuals         [LLM]
├── orgs/<slug>.md     institutions (BKC, EFF, Data & Society…)       [LLM]
├── events/<slug>.md   concrete occurrences: talks, papers, events   [LLM]
├── sources/
│   ├── _domains.md    domain → count table                          [SCRIPT]
│   └── <domain>.md    optional notes on a notable source            [LLM]
├── timeline/
│   ├── _counts.md     year/month → count tables                     [SCRIPT]
│   └── <year>.md      per-year narrative                            [LLM]
├── raw/
│   ├── digest.md      index of per-year digests                     [SCRIPT]
│   ├── digest/<year>.md   1 row/item: link · date · domain · tags   [SCRIPT]
│   ├── feed-tags.md   folksonomy tag counts (reference)             [SCRIPT]
│   └── .synthesis-state.json  ids already considered by synthesis   [SCRIPT]
├── collection/        RAG-ready source layer (additive)             [SCRIPT]
│   ├── collection.json   ingestion manifest (id, defaults, sources)
│   ├── json/youtube.json metadata catalog — 1 entry/video + transcript pointer
│   └── txt/youtube/yt_<id>.txt   one plain-text transcript per video
└── scripts/
    ├── build.mjs          the wiki generator                        [code]
    ├── fetch_youtube.py       @BKCHarvard scraper → collection/      [code]
    ├── fetch_youtube_api.py   @BKCHarvard Data API fetch → collection/ [code]
    ├── merge_youtube_into_archive.py  collection/ → raw/archive.json [code]
    ├── fetch_tagteam.py   hub 1176 Export feed → raw/archive.json    [code]
    ├── fetch_publications.py  cyber.harvard.edu/publications → raw/archive.json [code]
    └── synthesize_wiki.py new items → people/events/orgs/topics      [code]
```

### The ownership rule — do not break it
- **[SCRIPT]** files are regenerated by `scripts/build.mjs`. **Never hand-edit
  them** (changes are lost on the next run). Filenames prefixed `_` are a visual
  reminder they're generated.
- **[LLM]** files are yours. `build.mjs` **never overwrites** them (it only *seeds*
  `index.md` and `log.md` if they don't exist yet). As of the daily
  `synthesize-wiki.yml` workflow, `people/`, `events/`, `orgs/`, `topics/`,
  `timeline/<year>.md`, `index.md`, and `log.md` also get automated writes
  from `scripts/synthesize_wiki.py` — still LLM-authored content (just via an
  API call instead of an interactive session), scoped to new items only. See
  §5's "Automated synthesis" for how it's kept in its lane: a hard path
  allowlist enforced in code, not just prompt instructions.
- `raw/archive.json` is the immutable source **for the original Buzz import
  and the original 6,925-item TagTeam export** — a wholesale external
  re-scrape is the only thing that should ever replace those existing items.
  Three scripts append new items to it going forward, none touching existing
  ids: `scripts/merge_youtube_into_archive.py` (new `yt_` items, run at the
  end of the daily `fetch-youtube-captions.yml`), `scripts/fetch_tagteam.py`
  (new numeric-id TagTeam items, run daily by `fetch-tagteam-items.yml`,
  incrementally syncing hub 1176's own Export feed), and
  `scripts/fetch_publications.py` (new `pub_` items, run daily by
  `fetch-publications.yml`, syncing BKC's own publications index). All three
  are deliberate, ongoing exceptions, not loopholes — see §5.
- `collection/` is also **[SCRIPT]**-owned (by `fetch_youtube.py` /
  `fetch_youtube_api.py`) — don't hand-edit it. It is **additive and
  self-contained**: both fetch scripts only ever *read* `archive.json` (for
  dedup) and write under `collection/`, so they never conflict with a
  re-scrape of the TagTeam/Buzz source. `merge_youtube_into_archive.py` is the
  one script that writes `archive.json`, and only appends lightweight `yt_`
  entries (description text, not the transcript) — see §5 for why.

> **Note on the metadata-only constraint (§1):** it holds for the TagTeam
> corpus. `collection/` is the exception — it intentionally carries full
> transcript **body text**, kept in its own files so the RAG ingestion
> framework can index it. See `llm_engine` `archive_rag_ingestion.md`.

---

## 3. The key architectural move — link toward items

Synthesis pages (topics/people/orgs/timeline) link **to** item stubs:
`[[<id>-<slug>|Readable Title]]`. In Obsidian, **backlinks appear automatically**
on the item page — so every connection shows up on the item without ever editing
the (script-owned) stub. This keeps the 6,925 stubs cheap and regenerable while
all cross-referencing lives in your synthesis pages.

**Practical consequence:** to file an item under a topic, you add a line to the
*topic* page, not the item page. Never edit item stubs to add links.

### Link & slug conventions
- Item link target is the stub basename `<id>-<slug>` (no path, no `.md`).
  Copy it **verbatim from `raw/digest/<year>.md`** — don't reconstruct slugs by hand.
- Cross-link synthesis pages liberally: `[[content-moderation]]`, `[[eff]]`,
  `[[berkman-klein-center]]`. A link to a page that doesn't exist yet is fine — it
  marks a page worth creating.
- Slugs are lowercase-kebab. Topic/person/org filenames: `topics/ai-governance.md`,
  `people/jonathan-zittrain.md`, `orgs/eff.md`.

---

## 4. Page formats

Add YAML frontmatter to every LLM page (powers Obsidian Dataview).

### Topic — `topics/<slug>.md`
```markdown
---
type: topic
title: AI Governance
item_count: 42
related: [content-moderation, platform-regulation]
---
# AI Governance

One or two paragraphs synthesizing what the archive says on this topic: the main
threads, how emphasis shifts over time, notable tensions or contradictions.

## Key items
- [[13109290-meta-ditches-fact-checkers-...|Meta Ditches Fact-Checkers]] — 2025-01-07 · wired.com — one-line why-it-matters
- ...

## Related
[[content-moderation]] · [[platform-regulation]] · [[eff]]
```

### Person — `people/<slug>.md`
Who they are, their relationship to BKC, why they recur. `## Items` = backlink list
to their stubs. `## Topics` / `## Affiliations` cross-links.

### Org — `orgs/<slug>.md`
What it is, its role in the archive (publisher? subject? convener?), `## Items`,
related topics/people.

### Event — `events/<slug>.md`
A concrete real-world occurrence (talk, paper publication, workshop, podcast
episode) that generated **≥2 archive items from different source types**. Events
are the bridge between Buzz announcements, YouTube recordings, TagTeam community
posts, and press coverage of the same thing.

**When to create:** 2+ items from different source categories reference the same
occurrence. Common signals:
- Buzz `events`-tagged item + YouTube video sharing a title phrase or person name
- TagTeam `bkc-happenings` post + YouTube recording within the same week
- Three-source cluster: Buzz announcement + TagTeam post + YouTube recording

```markdown
---
type: event
title: "Internet Law at the Frontier — BKC Annual Symposium 2019"
date: 2019-10-15          # or YYYY-MM if only month is known
venue: "Harvard Law School"   # optional
participants: ["Jonathan Zittrain", "Evelyn Douek"]
related_topics: [content-moderation-and-speech]
related_people: [jonathan-zittrain]
related_orgs: [berkman-klein-center]   # optional
---
# Internet Law at the Frontier — BKC Annual Symposium 2019

One paragraph: what the event was and why it matters to BKC's work.

## Items

- [[buzz_201910_3|Berkman Buzz, Oct 2019]] — buzz: advance announcement
- [[yt_AbCdEfGhIjK-internet-law-at-the-frontier|Video title]] — youtube: full recording
- [[13204567-event-page-title|Event page (TagTeam)]] — tagteam: programme notes

## Related
[[jonathan-zittrain]] · [[content-moderation-and-speech]]
```

**Slug convention:** `<YYYY>-<short-title>`, e.g. `2019-symposium-internet-law-frontier`.

### Timeline — `timeline/<year>.md`
Narrative of that year's dominant themes (read `raw/digest/<year>.md`), a handful
of highlight items, and links to the topic pages that peaked that year.

### index.md
Catalog by category — Topics, People, Organizations, Sources, Timeline, plus the
generated Reference pages. Each line: `[[link]] — one-line summary (count)`. Update
it whenever you add/rename a synthesis page.

### log.md
Append-only. Every entry starts `## [YYYY-MM-DD] <op> | <detail>` so
`grep '^## \[' log.md | tail -5` works. `<op>` ∈ {build, ingest, synthesis, query,
lint, fetch}.

---

## 5. Operations

### Build / refresh (run the script)
```bash
node scripts/build.mjs --year=2025   # default; one year of stubs
node scripts/build.mjs --all         # every item, all years
```
Counts, digests and tag tables are always computed corpus-wide; only stub pages are
gated by `--year`. Idempotent — re-run any time; it cleans the year folder(s) it
rewrites so renamed/removed items don't leave orphans.

### Fetch YouTube transcripts — two mechanisms, same `collection/` layout
Both write one metadata entry per video to `collection/json/youtube.json`
(shaped like an `archive.json` item, plus `youtube` + `transcript` blocks) and
one plain-text transcript per video to `collection/txt/youtube/yt_<id>.txt`.
They share dedup state (`youtube_common.py`), so either can resume where the
other left off.

**`scripts/fetch_youtube_api.py` (official, ToS-compliant, runs daily in CI)**
— the official YouTube Data API v3, OAuth-authenticated as a BKCHarvard
channel manager. This is what `.github/workflows/fetch-youtube-captions.yml`
runs on a `17 6 * * *` cron: fetch, budgeted to stay under the free
10,000-units/day quota (~40 videos/day, so the ~1,100-video backlog takes
about a month), then `merge_youtube_into_archive.py` (below), then commit +
push both `collection/` and `raw/archive.json` together. Needs
`YT_OAUTH_CLIENT_ID` / `YT_OAUTH_CLIENT_SECRET` / `YT_OAUTH_REFRESH_TOKEN` as
repo secrets — see the script's docstring for how to mint them and where they
go (repo secrets for CI; shell-exported or a local `.env` for manual runs, but
this script doesn't auto-load `.env`, so `set -a; source .env; set +a` first).
Until those secrets are set, the workflow no-ops daily instead of failing.

```bash
python3 scripts/fetch_youtube_api.py --dry-run        # enumerate only (works with just YT_API_KEY)
python3 scripts/fetch_youtube_api.py --limit 5         # small test run
python3 scripts/fetch_youtube_api.py                   # full run, budgeted 9750 units
```

**`scripts/fetch_youtube.py` (scraper, manual/local only, not in CI)** —
YouTube's internal Innertube API + `youtube-transcript-api`. Predates the
Data API script; kept as a faster (no quota limit) fallback for manual local
runs, but it isn't the sanctioned access path (see the ToS discussion this
whole pipeline grew out of), so it's not what the daily workflow uses.

```bash
pip install youtube-transcript-api requests           # one-time
python3 scripts/fetch_youtube.py --dry-run            # list new videos, no writes
python3 scripts/fetch_youtube.py --limit 5            # small test run
python3 scripts/fetch_youtube.py                      # full run (resumable)
```

- **Resumable & idempotent** (both scripts). Each transcript is written immediately
  and progress is staged to `collection/json/.youtube-staging.json` (atomic writes).
  Re-run to continue — already-cataloged videos and blocked videos are
  skipped/retried automatically; nothing duplicates. Neither fetch script writes
  `archive.json` — only `merge_youtube_into_archive.py` does (see below).
- **YouTube IP-blocks bulk transcript fetching** (~50 requests/IP) — this only
  applies to the scraper. The script distinguishes a genuine "no captions"
  (cataloged once) from a rate-limit *block* (never cataloged → retried later),
  and aborts cleanly after `BLOCK_ABORT_THRESHOLD` consecutive all-proxy blocks.
- **Proxies** beat the scraper's block. Put one proxy per line in `scripts/.proxies`
  (gitignored; Webshare's `host:port:user:pass` "Proxy List" export works as-is)
  and the script rotates across them on a block:
  ```bash
  YT_PROXY_FILE=scripts/.proxies python3 scripts/fetch_youtube.py
  ```
  Webshare *free* = datacenter proxies (often still blocked by YouTube); paid
  *residential* is more reliable. With all proxies in cooldown, wait and re-run.
  See `load_proxy_configs()` in the script for all env-var options.
- Log a `## [date] fetch | youtube …` entry afterward.

### Merge YouTube videos into `archive.json` (`scripts/merge_youtube_into_archive.py`)
Folds `collection/json/youtube.json` entries into `raw/archive.json` — the
step that gets YouTube videos an item stub the next time `build.mjs` runs.
Mirrors `import_buzz.py`'s merge pattern (skip ids already present, merge,
sort by `date_published`, write) but is meant to be **re-run repeatedly**, not
a one-time import: every run only appends `yt_` ids not yet in `archive.json`,
so it's safe to call daily (it runs automatically at the end of
`fetch-youtube-captions.yml`) or by hand at any time.

```bash
python3 scripts/merge_youtube_into_archive.py --dry-run   # report only
python3 scripts/merge_youtube_into_archive.py             # merge new videos
```

Deliberately does **not** inline transcript text into `archive.json` — a
transcript can be tens of KB per video, and `archive.json` is one shared
7,000+-item file; duplicating ~1,100 transcripts into it would bloat it by
tens of MB for no benefit. The merged item's `content` is the (short) video
description; the full transcript stays exactly where the fetch scripts put
it, one `.txt` per video, referenced via `transcript.path`.

### Fetch TagTeam items (`scripts/fetch_tagteam.py`)
Incrementally syncs BKC's own TagTeam hub 1176
(tagteam.harvard.edu/hubs/1176) into `raw/archive.json` daily, via
`fetch-tagteam-items.yml` (cron `47 6 * * *`, 30 min after the YouTube
workflow so the two don't race on the same push). No credentials needed —
the hub's `items.json`/`items.rss` are its own public "Export" feature.

```bash
python3 scripts/fetch_tagteam.py --dry-run   # report only, no writes
python3 scripts/fetch_tagteam.py             # fetch + merge new items
```

- **How it works:** two calls per page — `items.json` for structured fields
  (numeric `id`, `url`, `tags`, dates), `items.rss` for the plain-text
  `description` (not present in the JSON) — merged by URL. Items come back
  `date_published`-descending; pages through until a full page has zero
  items not already in `archive.json` by id, then stops.
- **Known limitation:** an old article tagged into the hub *today* sorts by
  its (old) `date_published`, not today's date, so it could in principle sit
  past the stopping point and be missed on the daily incremental sync — rare
  in practice since BKC's curators tag things near publish time, and the
  periodic full re-scrape described below remains the safety net for
  anything this misses.
- **Politeness:** confirmed via testing that the site does rate-limit (a
  429) — the script retries with backoff, waits between pages, and sends a
  descriptive `User-Agent`. Don't lower `PAGE_DELAY`/remove the backoff
  without re-confirming the site can take it.
- Log a `## [date] fetch | tagteam …` entry afterward.

### Fetch BKC publications (`scripts/fetch_publications.py`)
Syncs BKC's own publications index (cyber.harvard.edu/publications) into
`raw/archive.json` daily, via `fetch-publications.yml` (cron `05 7 * * *`,
between TagTeam and Synthesis). No credentials needed — it's a public page.

```bash
python3 scripts/fetch_publications.py --dry-run --limit 5   # small sanity check
python3 scripts/fetch_publications.py                        # fetch + merge new items
```

- **Why BKC's own page, not SSRN directly:** there's no single SSRN eJournal
  aggregating BKC's output (papers just carry a "Berkman Klein Center
  Research Publication No." label individually — nothing to follow), and
  SSRN itself sends explicit anti-automation signals: `robots.txt` blocks
  `GPTBot`/`ChatGPT-User`/`Google-Extended` by name, a direct request gets
  Cloudflare's bot-challenge block, and the response carries a
  `tdm-reservation: 1` header — Elsevier's formal Text-and-Data-Mining
  opt-out signal. Unlike TagTeam or this website (BKC's own tools), SSRN is
  a third-party commercial platform with no institutional relationship
  giving standing here, so this script **never touches SSRN**. BKC's own
  publications page already links out to SSRN/DASH per entry, so the wiki
  still ends up linking to SSRN — just via BKC's own citation.
- **How it works:** pages `/publications?page=N` (confirmed
  reverse-chronological); for each entry not already covered, fetches its
  detail page for title/date/authors/abstract/topics/external links.
  BeautifulSoup-based (the listing/detail HTML has real structure worth
  parsing properly, unlike the simple meta-tag regexes elsewhere in this
  repo). Same incremental strategy as `fetch_tagteam.py` — stops once a
  full page has nothing new. Full `YYYY-MM-DD` dates come straight from each
  detail page's `<time datetime="...">` — exact, not just year/month.
- **Three URL schemes across BKC's history, all handled:**
  `/publication/<year>/<slug>` (current), `/publications/<year>[/<mm>]/<slug>`
  (old, plural — the scheme some already-archived TagTeam items use too),
  and bare `/node/<nid>` for the oldest content with no slug alias at all.
  The listing selector and `derive_id` both match all three — matching only
  the current scheme made pages several years back look "empty" (0 real
  publication links, even though `c-unique-item` blocks were present) and
  falsely tripped the stop-on-nothing-new logic partway through history.
- **First run is slow, on purpose:** 0 `pub_` items exist yet, so nothing
  stops the walk early — it processes the full history in one go (BKC's
  publications page goes back to 1993; the first real run merged 330 items,
  reaching e.g. Zittrain/Nesson/Lessig's 1999 "Open Code / Open Content /
  Open Law"). Not capped, since there's no hard quota (unlike YouTube's Data
  API); daily runs after that are fast (usually 0-1 pages).
- **Resumable, like the YouTube scripts:** each item is staged to
  `raw/.publications-staging.json` (atomic write) immediately after it's
  built, merged into `archive.json` only at the end. A crash mid-run loses
  at most the one item in flight — testing surfaced that this site's
  connections go stale after the per-request delay (every request failing
  once before succeeding on retry), so a long historical run is exactly
  the kind of thing worth checkpointing rather than trusting to finish
  in one uninterrupted shot.
- **`Connection: close`** on the session fixed that staleness issue
  outright (a fresh connection per request costs a handshake, but that's
  far cheaper than the 8s+ backoff a stale-connection reset was costing on
  nearly every single request before this).
- **Dedup by URL, not just id:** several publications are already in
  `archive.json` via incidental TagTeam bookmarking, under a numeric id
  rather than this script's `pub_<year>-<slug>` scheme — skip if the
  publication's own URL *or* an external link found on its detail page
  (SSRN/DASH) matches an existing item's `url`. URL comparison is
  scheme-normalized (`normalize_url`) since some existing entries were
  captured years ago as `http://`, not `https://` — an easy dedup miss if
  compared as exact strings.
- **Politeness:** `robots.txt` carries a `Crawl-delay: 15` scoped to one
  specific block, but applying it as the general rule is the safe read;
  retry+backoff; a descriptive `User-Agent`.
- **DASH is not integrated (yet).** DASH (`dash.harvard.edu`) has no
  `robots.txt` restrictions and a real public API (LibraryCloud,
  `api.lib.harvard.edu/v2/items.json`, confirmed live/JSON/unauthenticated),
  but no clean way to scope a query to "Berkman Klein Center" specifically
  was found (`repository=DASH` → 0 results, `collection=` → undefined Solr
  field error) within a reasonable research effort — plain full-text author
  search works (e.g. 64 hits for "Zittrain") but isn't reliably
  affiliation-scoped, so it'd add noise (matches on name alone, not
  BKC-authorship) to an unattended daily job rather than clean coverage.
  Follow-up if picked back up: either find real LibraryCloud field docs
  beyond what's publicly indexed, or query per known `people/*.md` author
  name and accept it as a partial supplement, not primary coverage.
- Log a `## [date] fetch | publications …` entry afterward.

### Ingest (a wholesale source re-scrape happened)
Distinct from the daily incremental `fetch_tagteam.py` sync above — this is
for when someone hands you an entirely fresh `raw/archive.json` export (not
one file at a time). Flow: re-run `build.mjs --all` → scan the newest rows in
`raw/digest/<latest>.md` → update/extend affected topic/person/org pages and
the relevant `timeline/<year>.md` → update `index.md` → append a
`## [date] ingest | …` log entry.

### Synthesis (build the value layer)
1. Read `raw/digest/<year>.md` for the slice you're working (one pass).
2. Cluster titles into topics. Create/extend `topics/*.md`; file each item by adding
   its `[[stub|Title]]` line under a topic's **Key items**.
3. Extract recurring people (authors + names in titles) and orgs; create their pages.
4. **Identify cross-source event clusters:** when a Buzz item, a YouTube video, and/or
   a TagTeam post appear to reference the same real-world occurrence (matching title
   phrases, person names, dates within ≤7 days), create an `events/<slug>.md` page.
   Link the event from relevant topic/person pages. See §4 for the event format.
5. Write/update `timeline/<year>.md`, refresh `index.md`, append a `synthesis` log entry.

Prefer working one year at a time. An item can appear under several topics and in one event.

### Automated synthesis (`scripts/synthesize_wiki.py`, daily)
Runs the same Synthesis workflow above, automatically, scoped to whatever's
new — via `synthesize-wiki.yml`, ~30-45 min after both fetch workflows.
Emphasizes **People and Events as coherent entities on equal footing with
Topics** — the point is making sure a YouTube video, a TagTeam bookmark, and
a Buzz item that are really about the same person or the same real-world
occurrence get filed under, and cross-linked from, one page (§3's "link
toward items" move), not left as three disconnected item stubs.

Two-pass design against OpenAI's API (an institutional key, not Claude Code
— see the script's docstring for why): Pass 1 plans which existing entities
each new item belongs under, or whether it warrants a new page (same ≥2-
different-source-types bar as the manual Event workflow above); Pass 2
drafts the actual updated/new page content for everything touched.

- **Scoped to new items only.** `raw/.synthesis-state.json` tracks which
  ids have already been considered. On its very first run (no state file
  yet) it seeds the baseline from every current id and synthesizes
  *nothing* — this pipeline does not attempt the historical backfill
  (most years are still "synthesis pending" per §6); that stays a
  separate, human-driven effort using the manual workflow above.
- **Depends on `build.mjs` having just run** (the workflow does this first)
  — item link slugs are read directly from the stub filenames under
  `items/<year>/`, never reconstructed by hand, for the same reason §3
  says to copy them verbatim from `raw/digest/<year>.md`.
- **Guardrails, enforced in code:** a hard allowlist of writable paths
  (rejects anything outside `people/`, `events/`, `orgs/`, `topics/`,
  `timeline/`, `index.md`, `log.md`, its own state file); `--max-items`
  defers any backlog beyond one run's cap to the next run rather than
  dropping it; `--max-cost-usd` stops before exceeding a cost ceiling.
- **Commits straight to `main`** like the fetch pipelines — no PR review.
  If quality drifts (mis-clustered entities, a page that shouldn't have
  been created), the existing Lint workflow below is the course-correction
  mechanism — treat an automated synthesis run's output the same as your
  own when lint-checking, not as exempt from scrutiny.
- Appends its own `## [date] synthesis | automated daily run` log entry —
  distinguish it from your interactive synthesis entries by that phrasing.

### Query (answer a question)
Read `index.md` → open the relevant topic/entity pages → drill into linked item
stubs → answer **with `[[…]]` citations**. **File good answers back** as a new page
(a `topics/` page, a comparison, an analysis) so explorations compound. Log it.

### Lint (health-check)
Look for: orphan topics (no inbound links), stale claims newer items supersede,
duplicate/near-duplicate pages, recurring names lacking a person/org page, topics
with too few items to justify a page (fold them in), broken `[[links]]`, and obvious
topic gaps in `raw/digest/*`. Report findings + suggested questions; fix what's
mechanical. Append a `lint` log entry.

---

## 6. Status

**Corpus:** 7,884 items and growing daily from three automated fetch
pipelines — TagTeam bookmarks (daily incremental sync via
`fetch-tagteam-items.yml`) + 417 Berkman Buzz newsletters (2006–2015,
one-time import) + BKC YouTube videos (~1,101 public videos;
`fetch-youtube-captions.yml` runs daily via the official Data API, budgeted
~39 new videos/day, so the backlog takes several more weeks unless a quota
increase is granted) + 374 BKC publications (`pub_` items, back to 1993,
fully backfilled; daily via `fetch-publications.yml`, syncing
cyber.harvard.edu/publications — not SSRN directly, see §5). The daily
`synthesize-wiki.yml` workflow exists but is currently dormant (no
`OPENAI_API_KEY` secret set yet) — set aside for now, not removed.

**Wiki build:** all years stubbed and digested (`--all`). Thematic synthesis covers
**2025** fully. Other years have navigational landing pages pending synthesis
— that historical backfill is still a human-driven effort (see Synthesis
above); the daily `synthesize-wiki.yml` workflow only ever processes items
newer than its `raw/.synthesis-state.json` baseline, never the backlog.

**Events layer:** 8 pages so far (recurring conferences/series populated in
batch 10 — see `log.md`), now growing incrementally via the daily automated
synthesis run in addition to interactive sessions. Priority clusters still
worth a manual pass:
- 2014–2015: TagTeam + Buzz overlap (earliest cross-source years)
- 2025: richest TagTeam data; YouTube videos now arriving daily

See `log.md` for history.
