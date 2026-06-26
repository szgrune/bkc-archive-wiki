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
