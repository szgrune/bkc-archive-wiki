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
