# Log

Append-only. Entry prefix: `## [YYYY-MM-DD] <op> | <detail>`.

## [2026-06-12] build | scaffolded wiki via scripts/build.mjs
Generated 737 item stubs for 2025; corpus-wide digest (per-year), sources/_domains.md, timeline/_counts.md, raw/feed-tags.md.

## [2026-06-12] synthesis | 2025 prototype slice
Clustered the 2025 digest (737 items) into the value layer:
- 11 topic pages: [[ai-governance-and-regulation]], [[ai-and-democracy]], [[surveillance-and-immigration-tech]], [[content-moderation-and-speech]], [[ai-labor-and-economy]], [[ai-safety-and-agents]], [[ai-and-the-environment]], [[ai-chatbots-and-mental-health]], [[digital-colonialism-and-global-south]], [[ai-copyright-and-knowledge]], [[platform-power-and-antitrust]].
- 6 people: [[rudy-fraser]], [[evelyn-douek]], [[bruce-schneier]], [[jonathan-zittrain]], [[tim-wu]], [[cindy-cohn]].
- 7 orgs: [[berkman-klein-center]], [[techpolicy-press]], [[404-media]], [[knight-first-amendment-institute]], [[rest-of-world]], [[lawfare]], [[electronic-frontier-foundation]].
- [[2025|timeline/2025]] narrative; rebuilt index.md.
Metadata-only (no URL fetches). Next: human review of formats in Obsidian, then `node scripts/build.mjs --all` + extend synthesis across all years.

## [2026-06-25] build | all years stubbed (2014–2026, 6,925 items)
Ran `scripts/build.mjs --all`: regenerated item stubs for every year (was 2025-only), plus corpus digests, _domains, _counts, feed-tags.

## [2026-06-25] lint | site-structure + formatting cleanup
- Generator (`build.mjs`): item titles now HTML-entity-decoded; `#hashtags` in titles escaped so Quartz renders them literally instead of auto-linking them as topic tags (slug derivation unchanged → stub filenames stable). Regenerated all stubs.
- Seeded navigational `timeline/<year>.md` landing pages for all un-synthesized years (seed-if-absent; 2025 narrative preserved).
- Fixed ambiguous year wikilinks: index Timeline, `_counts.md`, and `digest.md` now use path-qualified targets (`[[timeline/<year>]]` / `[[raw/digest/<year>]]`) to resolve the `2025` basename collision. Index Timeline now lists all 12 years.
- Added `.quartz/custom.scss` (explorer-sidebar scroll fix) injected via `deploy.yml`.

## [2026-06-26] ingest | Berkman Buzz emails + events layer infrastructure
- Added 417 Berkman Buzz newsletters (2006–2015) to `raw/archive.json` via `scripts/import_buzz.py`. IDs: `buzz_YYYYMM_N`. Full body text + email metadata included. Total corpus: 7,342 items.
- Introduced `events/` as a new LLM-owned entity type (alongside topics/people/orgs). See `AGENTS.md §4` for schema and detection heuristics.
- Updated `AGENTS.md`: corpus section, layout tree, page formats, synthesis workflow, status.
- Updated `index.md`: scope note, added Events section, extended Timeline to include Buzz years (2006–2015).
- Rebuilt all stubs: `scripts/build.mjs --all` → 7,342 stubs across 2006–2026.
- Events synthesis pending: priority years are 2014–2015 (first TagTeam+Buzz overlap) and 2025 (richest TagTeam data; YouTube to follow).

The global graph used Quartz's default `depth: -1`, rendering every page (~6.9k nodes, mostly unlinked item stubs) and hanging the browser. `deploy.yml` now seds `quartz.layout.ts` to `Component.Graph({ globalGraph: { depth: 3 } })` — a bounded BFS that loads fast and shows only the linked cluster. Local/mini graph unchanged (`depth: 1`).

## [2026-06-26] synthesis | corpus-wide topics, batch 1 (6 cross-cutting pages)
Began extending the value layer beyond the 2025 slice to span 2006–2026. Added 6
durable cross-cutting topic pages, each curated from the per-year digests (verbatim
stub links) across the full timeline:
- [[privacy-and-surveillance]], [[misinformation-and-elections]], [[journalism-and-the-news-business]], [[copyright-and-open-access]], [[cybersecurity-and-encryption]], [[facial-recognition-and-deepfakes]].
Updated index.md (Topics section + scope note). Cross-links to not-yet-created
entity pages (e.g. [[data-society]], [[nieman-lab]], [[citizen-lab]], [[ethan-zuckerman]],
[[lawrence-lessig]], [[woodrow-hartzog]], [[creative-commons]]) are intentional and
seed the next batches. Metadata-only (no URL fetches).
Next: orgs (Data & Society, Global Voices, Creative Commons, Citizen Lab, Nieman Lab,
CITP, The Markup…), Buzz-era + TagTeam people, remaining topics (net neutrality,
algorithmic accountability), and Buzz↔TagTeam event clusters; then extend the existing
2025 pages corpus-wide.

## [2026-06-26] synthesis | corpus-wide orgs, batch 2 (6 org pages)
Added 6 organization pages for high-frequency ecosystem actors, curated from domain
(and, for Buzz-era projects, title) matches in the digests:
- [[data-society]], [[citizen-lab]], [[nieman-lab]], [[global-voices]], [[the-markup]], [[princeton-citp]].
Updated index.md Organizations section. Skipped thin candidates below the recurrence
threshold (Creative Commons 2 items, EPIC 3) — folded as cross-links instead.
Cross-links seed people pages still to come ([[danah-boyd]], [[ethan-zuckerman]]).
Next batch: people (Buzz-era BKC figures + TagTeam-era scholars).

## [2026-06-26] synthesis | corpus-wide people, batch 3 (6 person pages)
Added 6 people pages spanning both archive eras, curated via featured Buzz columns
(content-matched "From <Name>") and TagTeam title matches → verbatim digest lines:
- Buzz-era BKC figures: [[ethan-zuckerman]], [[david-weinberger]], [[john-palfrey]], [[lawrence-lessig]].
- Cross-era: [[danah-boyd]] (Data & Society founder), [[woodrow-hartzog]] (privacy-law theorist).
Updated index.md People section. These resolve several cross-links seeded by the
topic/org batches. Next: events (Buzz↔TagTeam clusters), remaining topics
(net neutrality, algorithmic accountability), then expand the existing 2025 pages.

## [2026-06-26] synthesis | topics batch 4 (2 more cross-cutting pages)
Added [[net-neutrality-and-internet-access]] (2014–18 peak + broadband equity) and
[[algorithmic-accountability]] (algorithmic curation → bias audits → "algorithms as
institutions"). Curated from year-stratified digest matches; filtered IEEE-Spectrum
false positives out of the net-neutrality pool. Updated index.md.
Topic layer now: 11 AI/2025 + 8 cross-cutting = 19 topic pages.
Remaining: events (Buzz↔TagTeam clusters, mostly the 2014–15 overlap) and expanding
the existing 2025-scoped pages corpus-wide.

## [2026-06-26] synthesis | events batch 5 + survey
Surveyed the corpus for cross-source / single-occurrence event clusters (scripted:
shared event-phrase buckets + near-duplicate-title pairs within 45-day windows).
Finding: genuine multi-facet events are structurally rare here — Buzz (2006–2015) and
TagTeam (2017+) barely overlap, and most TagTeam "clusters" are syndication duplicates
(same wire story across outlets) or recurring seminar series (CITP, lecture series),
not one occurrence reported from multiple angles. Created the one clean qualifying
event: [[2017-privacy-tools-for-data-sharing]] (Harvard Privacy Tools Project symposium;
event page + registration). Fixed index.md Events section (was "none yet" despite the
existing [[2014-privacy-at-the-margins]]) and documented the structural limitation.
Richer event synthesis is deferred to the YouTube import (the missing second source type).

## [2026-06-26] synthesis | expand existing orgs corpus-wide (batch 6)
Backfilled pre-2025 items into the four highest-backlog existing org pages, folding the
earlier-era context into each intro: [[techpolicy-press]] (→2021), [[rest-of-world]]
(→2021), [[404-media]] (→2023), [[lawfare]] (→2019). Verbatim digest lines. Updated
index.md counts. EFF (12 items, mostly events) and Knight (30, already 2025-era) left as
adequately scoped. Remaining expand-existing: deepen [[jonathan-zittrain]] and
[[bruce-schneier]] from their rich Buzz-era histories; light era notes on the AI topics.

## [2026-06-26] synthesis | deepen foundational people (batch 7)
Expanded the two thinnest-but-most-central existing people pages from 1 item to full
corpus-wide arcs: [[jonathan-zittrain]] (2014→2025: right-to-be-forgotten, intellectual
debt, the Great Deplatforming, AI agents & trust) and [[bruce-schneier]] (2020→2026:
security thinking → *A Hacker's Mind* → AI security & AI-and-democracy). Updated index
counts. The other existing people (rudy-fraser, evelyn-douek, cindy-cohn, tim-wu) are
genuinely 2025-specific figures with little earlier presence — left as scoped.

This completes the corpus-wide synthesis expansion pass. Layer now: 19 topics,
13 orgs, 12 people, 2 events. AI-cluster topics remain 2025-anchored by design (AI was
not a dominant thread before ~2022); cross-cutting topics and the major orgs/people now
span 2006–2026.

## [2026-06-26] synthesis | timeline narratives, Buzz era 2006–2016 (batch 8)
Wrote per-year narratives for all Buzz-era years. 2006–2010 themes mined from newsletter
*body content* (titles are generic "Berkman Buzz, week of X"): 2006 blogosphere/Tor/
StopBadware/China; 2007 Global Voices + Citizen Media Law + OpenNet; 2008 election +
Internet&Democracy + Digital Natives + Zittrain/generativity; 2009 Iran "Twitter
Revolution" + Herdict; 2010 WikiLeaks + Google–China + Facebook privacy. 2011–2015 from
thematic digest titles (SOPA/Arab Spring; open access; Snowden/Aaron Swartz; net
neutrality/encryption; the Buzz sign-off). 2016 documented as the source-transition seam
(4 items). Fixed stale frontmatter on timeline/2014 (item_count 2 → 48, pre-Buzz-merge).

## [2026-06-26] synthesis | timeline narratives, TagTeam era 2017–2026 (batch 9)
Wrote per-year narratives for all TagTeam years, grounded in per-year theme-keyword
profiles over titles: 2017 feed-online/2016-reckoning; 2018 Cambridge Analytica/techlash;
2019 (largest year) AI-ethics + facial recognition; 2020 pandemic/protest/disinfo
election; 2021 Jan-6/Great Deplatforming/Facebook Papers; 2022 Musk's Twitter + the
generative-AI dawn; 2023 the ChatGPT year; 2024 the global "AI election"; 2026 the
AI-saturated continuation. Rewrote the index.md Timeline section so every year carries a
one-line theme (was "synthesis pending"). All 21 years (2006–2026) now have narratives.

## [2026-06-26] synthesis | events — recurring conferences & series (batch 10)
Populated the events layer from the existing corpus with recurring named conferences/
series (instances grouped one page per series, verbatim links): [[rightscon]] (2017–26),
[[we-robot]] (2019–25), [[citp-seminar-series]] (sampled), [[harvard-data-science-initiative]]
(2018–21), [[internet-freedom-festival]] (2016–19), [[privacy-law-scholars-conference]].
Restructured index.md Events into "cross-source clusters" + "recurring conferences &
series." This is the looser, pre-YouTube events population the user asked for; per-edition
dedup/refinement is deferred to the YouTube import (currently blocked on rate-limit/budget
for full-channel transcript scraping). Events layer now: 8 pages.

## [2026-06-26] lint | rename home/title-bar text (Quartz 4 → BKC Archive Wiki)
The top-left home link rendered Quartz's default `pageTitle` ("Quartz 4"). `pageTitle`
lives in the cloned Quartz tree's `quartz.config.ts`, not this content repo, and the
deploy workflow wasn't overriding it. Added a sed in `.github/workflows/deploy.yml`
(alongside the existing baseUrl/graph seds) to set `pageTitle: "BKC Archive Wiki"` at
build time. Link target unchanged (still the site root). Verified locally.

## [2026-07-13] build | rebuild stubs for YouTube + TagTeam daily-fetch backlog
Ran `scripts/build.mjs --all` to catch up item stubs/digests for the items merged by
the new daily fetch pipelines since they went live (88 YouTube videos, 38+ TagTeam items).
Corpus now 7,468 items, all with stubs. Routine housekeeping ahead of wiring up the daily
synthesis workflow, which depends on `raw/digest/<year>.md` being current for slug lookups.

## [2026-07-14] synthesis | manual pass over 42 new YouTube items (2021–2023)
`git pull` brought in the daily `fetch-youtube-captions.yml` run's latest merge (39 new
`yt_` items into `raw/archive.json`, 130 YouTube videos total now). Sanity-checked the
new transcripts before synthesizing: timestamps monotonic, no repeated-line/caption-spam
patterns, 135–210 wpm (normal speech rate), one legitimately caption-less video
(`yt_KVViqYD_4Lc`, `available: false` in `collection/json/youtube.json`, not a fetch bug).
Ran `scripts/build.mjs --all` for fresh stub slugs, then did the manual Synthesis workflow
(AGENTS.md §5) by hand rather than `scripts/synthesize_wiki.py` — per user instruction,
not because the script is broken. Diffed `raw/.synthesis-state.json`'s `processed_ids`
against current archive ids (42 unprocessed, all `yt_`, 2021–2023) to scope the work.

Filed all 42 items: 34 into existing topic pages (heaviest: content-moderation-and-speech
+9, privacy-and-surveillance +5, ai-governance-and-regulation +5), 3 BKC-internal
recruiting/info-session videos linked only from [[berkman-klein-center]] and
[[institute-for-rebooting-social-media]], and 8 into two new **Events** — the archive's
first events built from a genuine multi-recording real-world occurrence rather than a
single TagTeam artifact: [[2023-future-of-the-internet-summit]] (5 videos, ASML launch,
feat. Barack Obama) and [[2023-rsm-genai-oversight-fireside-series]] (3-part series).
Created 3 new org pages for BKC sub-initiatives that recur heavily in this batch —
[[institute-for-rebooting-social-media]], [[applied-social-media-lab]],
[[cyberlaw-clinic]] — and 4 new people pages for names confirmed recurring corpus-wide
via grep before creating a page (not just this batch's single mention): [[kendra-albert]]
(29 corpus mentions), [[cory-doctorow]] (11), [[joan-donovan]] (8), [[leah-plunkett]] (8).
Extended [[jonathan-zittrain]] and [[lawrence-lessig]] with their new items. Updated
item_count/Key items on every touched topic/org/person page, timeline/2021–2023.md
narratives and counts, and index.md (also caught timeline/2024–2026.md counts drifting
stale from the daily TagTeam sync while already in that section — 2024 917→952, 2025
737→769, 2026 444→497; unrelated to this batch but cheap to fix in passing). Marked all
42 ids processed in `raw/.synthesis-state.json` so the daily automated `synthesize-wiki.yml`
run doesn't redo this work.

## [2026-07-14] fetch | publications — daily sync of cyber.harvard.edu/publications live
Added scripts/fetch_publications.py + fetch-publications.yml: syncs BKC's own publications
index into archive.json daily (pub_ ids), not SSRN directly — SSRN sends explicit
anti-automation signals (robots.txt blocks AI crawlers by name, Cloudflare bot-challenge,
a TDM-reservation header), whereas BKC's own page is unrestricted and already links out to
SSRN/DASH per entry with an abstract. First run fully backfilled the historical archive:
374 items back to 1993 (Fisher/Horwitz's "American Legal Realism"), including foundational
BKC work like Zittrain/Nesson/Lessig's 1999 "Open Code / Open Content / Open Law". Handles
three URL schemes across BKC's history (/publication/, old-plural /publications/, bare
/node/<nid>) after an early version silently missed pre-2018 entries matching only the
current scheme. Resumable (staged writes) after testing surfaced the site's connections
going stale between requests; fixed outright with `Connection: close`. DASH (LibraryCloud
API) investigated as a supplement but not integrated — no clean way found to scope a query
to BKC affiliation specifically within a reasonable effort; documented as a follow-up.

## [2026-07-14] synthesis | manual pass over 374 BKC publications (1993–2026)
Manual synthesis (AGENTS.md §5) of the full `pub_` backfill — by far the largest single
batch to date, and the first to touch pre-2006 history. Ran `scripts/build.mjs --all`
for fresh stubs, then worked from BKC's own `publication.topics` categorization (189/374
items tagged, 8 categories) rather than re-deriving topics from titles alone, since this
source — unlike TagTeam — carries real BKC-authored subject tags.

**4 new topic pages**, each a defining BKC research program the AI-cluster topics don't
cover: [[internet-governance-and-icann]] (ICANN, interoperability, multistakeholder
governance), [[internet-filtering-and-openness]] (the OpenNet Initiative's
Access Denied/Controlled/Contested trilogy + Internet Monitor), [[digital-natives-and-youth-privacy]]
(*Born Digital* and a decade of youth-privacy empirical work), and
[[internet-democracy-and-networked-protest]] (blogosphere-mapping optimism 2007–2013
pivoting to the *Network Propaganda* media-ecosystem critique 2017–2020 — same research
team, inverted conclusion). **6 existing topics extended**:
[[privacy-and-surveillance]], [[cybersecurity-and-encryption]],
[[copyright-and-open-access]] (Lessig's and Benkler's actual founding texts, not just
Buzz-era coverage of them), [[net-neutrality-and-internet-access]],
[[ai-governance-and-regulation]] (an 8-years-early 2017 framework), and
[[digital-colonialism-and-global-south]].

**10 new people pages** for authors confirmed recurring corpus-wide before creating a
page (not just this batch): [[urs-gasser]] (86 items — BKC's most-published author by
far), [[robert-faris]] (32), [[sandra-cortesi]] (22), [[hal-roberts]] (17),
[[bruce-etling]] (14), [[yochai-benkler]] (13), [[john-kelly]] (12), [[david-obrien]]
(10), [[susan-crawford]] (9), [[william-fisher]] (6, but foundational — the corpus's
earliest author by date). **7 existing people pages substantially deepened** with their
actual authored works, not just Buzz-era coverage: [[jonathan-zittrain]] (the Access
Denied trilogy, "The Generative Internet," Don't Panic), [[john-palfrey]] (same
trilogy, *Born Digital*, *Interop*), [[lawrence-lessig]] (his actual 1999–2006 books:
*Code*, *Free Culture*, *The Future of Ideas*), [[david-weinberger]] (*Cluetrain*,
*Small Pieces*, *Everything is Miscellaneous*), [[danah-boyd]] (2007–2012 youth-safety
research predating *It's Complicated*), [[bruce-schneier]] (the 2016 encryption survey
and "Don't Panic"), and [[ethan-zuckerman]] (2003–2009 OpenNet/Media Re:public work).

**Timeline:** wrote first-ever narratives for 1993, 1997–2005 (previously bare
navigational stubs — no Buzz/TagTeam coverage exists that far back, so these years are
now 100% publications-sourced) and enriched 2006–2020 with cross-links to the new
topics/people, correcting each year's `item_count` and — where the added material
changed the actual story, not just the count — the narrative itself (2016 was
previously described as "the quiet seam" with only 4 items; it's actually one of BKC's
busiest research years, just invisible to the Buzz/TagTeam feeds).

Updated index.md scope line, all three lists (Topics/People/Timeline), and every touched
page's `item_count`. Appended this entry and marked all 374 `pub_` ids processed in
`raw/.synthesis-state.json`.
