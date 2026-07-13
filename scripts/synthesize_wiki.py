#!/usr/bin/env python3
"""
scripts/synthesize_wiki.py — daily automated synthesis of new archive.json
items into the wiki's People/Events/Orgs/Topics value layer.

Companion to the daily fetch pipelines (fetch_youtube_api.py,
fetch_tagteam.py): those append new items to archive.json; this turns new
items into wiki content, emphasizing People and Events as coherent entities
(not just Topics) — matching AGENTS.md §3's "link toward items" architecture,
so a YouTube video, a TagTeam bookmark, and a Buzz item about the same person
or the same real-world event get filed under, and cross-linked from, the
same page.

Requires `node scripts/build.mjs --all` to have been run first (the daily
workflow does this) — item link slugs are read directly from the stub
filenames build.mjs writes under items/<year>/, never reconstructed by
hand (build.mjs's slugify has its own truncation/dedup logic — see
AGENTS.md §3's "copy verbatim" rule this mirrors for the same reason).

Two-pass design against OpenAI's API (not Claude Code — this runs on an
institutional OpenAI key, not tied to any one person's subscription):

  Pass 1 (plan): given new items + a lightweight index of existing entity
  pages (slug/title/one-line gist, not full bodies), ask which existing
  entities each item belongs to, or whether it warrants a new page.

  Pass 2 (draft): for each entity actually touched, fetch its current full
  content (if any) + its assigned new items, ask for the complete updated
  page content following AGENTS.md §4's exact formats.

State — raw/.synthesis-state.json (committed, [SCRIPT]-owned): the set of
item ids already considered. Doesn't exist yet on the very first run: that
run seeds the baseline from every current id and synthesizes nothing — this
pipeline is scoped to new items going forward, not a historical backfill
(most years are still "synthesis pending" per AGENTS.md §6; that stays a
separate, human-driven effort).

Guardrail: every proposed file write is checked against a hard allowlist
(people/, events/, orgs/, topics/, timeline/, index.md, log.md, the state
file itself) before being applied — enforced in code, not just via prompt,
since this commits straight to main with no review step.

Usage:
    python3 scripts/synthesize_wiki.py --dry-run
    python3 scripts/synthesize_wiki.py --max-items 100 --max-cost-usd 2.0
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

WIKI_ROOT = Path(__file__).parent.parent
ARCHIVE_PATH = WIKI_ROOT / "raw" / "archive.json"
STATE_PATH = WIKI_ROOT / "raw" / ".synthesis-state.json"
ITEMS_DIR = WIKI_ROOT / "items"
PEOPLE_DIR = WIKI_ROOT / "people"
EVENTS_DIR = WIKI_ROOT / "events"
ORGS_DIR = WIKI_ROOT / "orgs"
TOPICS_DIR = WIKI_ROOT / "topics"
TIMELINE_DIR = WIKI_ROOT / "timeline"
INDEX_PATH = WIKI_ROOT / "index.md"
LOG_PATH = WIKI_ROOT / "log.md"

ENTITY_DIRS = {"person": PEOPLE_DIR, "event": EVENTS_DIR, "org": ORGS_DIR, "topic": TOPICS_DIR}

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")
# Rough per-1M-token estimates for cost logging only (not billing-accurate;
# update if the model changes materially).
EST_COST_PER_1M_INPUT = 3.0
EST_COST_PER_1M_OUTPUT = 15.0


# ── guardrail ──────────────────────────────────────────────────────────────

def is_path_allowed(path):
    """Hard allowlist enforced in code — the model's output is never trusted
    to only touch these paths on its own."""
    resolved = path.resolve()
    if resolved in (INDEX_PATH.resolve(), LOG_PATH.resolve(), STATE_PATH.resolve()):
        return True
    for d in (PEOPLE_DIR, EVENTS_DIR, ORGS_DIR, TOPICS_DIR, TIMELINE_DIR):
        try:
            resolved.relative_to(d.resolve())
        except ValueError:
            continue
        return resolved.suffix == ".md"
    return False


# ── state ──────────────────────────────────────────────────────────────────

def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return None


def save_state(processed_ids, dry_run):
    payload = json.dumps({"processed_ids": sorted(processed_ids)}, indent=2)
    if dry_run:
        print(f"[dry-run] would write {STATE_PATH.relative_to(WIKI_ROOT)} "
              f"({len(processed_ids)} ids)")
    else:
        STATE_PATH.write_text(payload, encoding="utf-8")


# ── frontmatter / entity index ───────────────────────────────────────────────

def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm_text, body = m.groups()
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def build_entity_index():
    index = []
    for kind, directory in ENTITY_DIRS.items():
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            first_line = next(
                (l.strip().lstrip("#").strip() for l in body.splitlines() if l.strip()), ""
            )
            index.append({
                "kind": kind, "slug": path.stem,
                "title": fm.get("title", path.stem), "gist": first_line[:200],
            })
    return index


def stub_target_for(item_id):
    """Exact '<id>-<slug>' stub basename from the file build.mjs already
    wrote under items/<year>/. Returns None if no stub exists yet (means
    `node scripts/build.mjs --all` needs to run first)."""
    for p in ITEMS_DIR.glob(f"*/{item_id}-*.md"):
        return p.stem
    return None


def source_label(item_id):
    if item_id.startswith("yt_"):
        return "youtube"
    if item_id.startswith("buzz_"):
        return "buzz"
    return "tagteam"


# ── OpenAI calls ─────────────────────────────────────────────────────────────

def call_openai(messages, max_tokens=4000):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY not set.")
    resp = requests.post(
        OPENAI_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": DEFAULT_MODEL, "messages": messages, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    return data["choices"][0]["message"]["content"], usage


def estimate_cost(usage):
    inp = usage.get("prompt_tokens", 0) / 1_000_000 * EST_COST_PER_1M_INPUT
    out = usage.get("completion_tokens", 0) / 1_000_000 * EST_COST_PER_1M_OUTPUT
    return inp + out


PASS1_SYSTEM = """You maintain the BKC Archive Wiki's synthesis layer: Markdown pages under \
people/, events/, orgs/, and topics/ that synthesize a large item archive, cross-linking \
items about the same person, event, organization, or topic.

Given NEW archive items and an index of EXISTING entity pages, decide, for each new item, \
which existing entities it belongs under, and whether it signals a page worth creating.

Rules:
- Only propose a NEW event page when the new items include at least 2 that reference the \
same real-world occurrence from DIFFERENT source types (e.g. a YouTube video AND a TagTeam \
bookmark about the same talk) — one item alone is never enough for a new event page.
- Only propose a NEW person/org page for a name/org that recurs meaningfully across items, \
not a passing mention in one.
- Strongly prefer attaching to an EXISTING entity (by slug) over creating a near-duplicate.
- An item can map to zero, one, or several entities (topics especially can be multiple).

Respond with JSON only:
{"assignments": [{"item_id": "<id>", "entities": [
  {"kind": "person|event|org|topic", "slug": "<existing-slug>"} |
  {"kind": "person|event|org|topic", "new_title": "<Proposed Title>"}
]}]}
"""

PASS2_SYSTEM = """You are updating ONE page of the BKC Archive Wiki's synthesis layer. \
Follow these formats exactly:

TOPIC (topics/<slug>.md):
---
type: topic
title: <Title>
item_count: <N>
related: [slug1, slug2]
---
# <Title>
<1-2 paragraphs synthesizing what the archive says on this topic>
## Key items
- [[<stub>|Title]] — date · domain — one-line why-it-matters
## Related
[[slug1]] · [[slug2]]

PERSON (people/<slug>.md):
---
type: person
title: <Name>
affiliations: [org-slug]
related_topics: [topic-slug]
---
# <Name>
<who they are, relationship to BKC, why they recur>
## Items
- [[<stub>|Title]] — date · domain
## Related
[[topic-slug]] · [[org-slug]]

ORG (orgs/<slug>.md): same shape as Person — what it is, its role in the archive, `## Items`, \
related topics/people.

EVENT (events/<slug>.md):
---
type: event
title: "<Title>"
date: <YYYY-MM-DD or YYYY-MM>
participants: ["Name1", "Name2"]
related_topics: [topic-slug]
related_people: [person-slug]
---
# <Title>
<one paragraph: what the event was and why it matters>
## Items
- [[<stub>|Title]] — <source>: <role, e.g. advance announcement / full recording / programme notes>
## Related
[[person-slug]] · [[topic-slug]]

You're given the entity's CURRENT content (empty string if new) and the new items assigned \
to it, each with its exact `stub` link target (already computed — use it verbatim, never \
invent or reconstruct a slug yourself) and `source` (youtube/tagteam/buzz). Merge new items \
into the existing content coherently — rewrite the synthesis paragraph if they change the \
picture, don't just append a bullet. Keep prose tight (this wiki cross-links liberally \
elsewhere; entity pages shouldn't duplicate topic-page synthesis).

Respond with JSON only: {"content": "<full markdown file content, frontmatter included>"}
"""


def run_pass1(new_items, entity_index):
    payload = {
        "new_items": [
            {
                "id": str(i["id"]), "title": i["title"], "url": i.get("url"),
                "date_published": i.get("date_published"), "tags": i.get("tags"),
                "description": re.sub(r"<[^>]+>", "", i.get("description") or "")[:500],
            }
            for i in new_items
        ],
        "existing_entities": entity_index,
    }
    content, usage = call_openai(
        [{"role": "system", "content": PASS1_SYSTEM},
         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        max_tokens=4000,
    )
    cost = estimate_cost(usage)
    print(f"  Pass 1: {usage} (~${cost:.3f})")
    try:
        return json.loads(content), cost
    except json.JSONDecodeError:
        print("  [warn] Pass 1 returned invalid JSON — skipping this run.", file=sys.stderr)
        return {"assignments": []}, cost


def run_pass2(entity, items_for_entity, existing_content):
    payload = {
        "kind": entity["kind"], "slug": entity["slug"], "title": entity["title"],
        "existing_content": existing_content or "",
        "new_items": [
            {"title": i["title"], "url": i.get("url"), "date_published": i.get("date_published"),
             "stub": i["_stub"], "source": source_label(str(i["id"]))}
            for i in items_for_entity
        ],
    }
    content, usage = call_openai(
        [{"role": "system", "content": PASS2_SYSTEM},
         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        max_tokens=3000,
    )
    cost = estimate_cost(usage)
    print(f"    Pass 2 ({entity['slug']}): {usage} (~${cost:.3f})")
    try:
        return json.loads(content).get("content"), cost
    except json.JSONDecodeError:
        print(f"  [warn] Pass 2 invalid JSON for {entity['slug']} — skipping.", file=sys.stderr)
        return None, cost


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-items", type=int, default=100)
    ap.add_argument("--max-cost-usd", type=float, default=2.0)
    args = ap.parse_args()

    archive = json.loads(ARCHIVE_PATH.read_text())
    all_ids = {str(i["id"]) for i in archive["items"]}

    state = load_state()
    if state is None:
        print(f"No {STATE_PATH.name} — seeding baseline with {len(all_ids)} ids. "
              f"This run synthesizes nothing; future runs process only new items "
              f"(historical backfill stays a separate, human-driven effort).")
        save_state(all_ids, args.dry_run)
        return

    processed_ids = set(state.get("processed_ids", []))
    new_items = [i for i in archive["items"] if str(i["id"]) not in processed_ids]
    print(f"{len(new_items)} new item(s) since last synthesis run.")
    if not new_items:
        return

    deferred = 0
    if len(new_items) > args.max_items:
        new_items.sort(key=lambda x: x.get("date_published") or "")
        deferred = len(new_items) - args.max_items
        new_items = new_items[:args.max_items]
        print(f"Capped at {args.max_items} items this run; {deferred} deferred to next run.")

    # Attach each item's real stub target now — items lacking one (build.mjs
    # hasn't run for them yet) are excluded rather than risking a broken link.
    ready_items, not_ready = [], []
    for i in new_items:
        stub = stub_target_for(str(i["id"]))
        if stub:
            i["_stub"] = stub
            ready_items.append(i)
        else:
            not_ready.append(i)
    if not_ready:
        print(f"  {len(not_ready)} item(s) have no stub yet (build.mjs needs to run "
              f"first) — left unprocessed, will retry next run.")
    if not ready_items:
        print("Nothing ready to synthesize this run.")
        return

    entity_index = build_entity_index()
    plan, total_cost = run_pass1(ready_items, entity_index)
    if total_cost >= args.max_cost_usd:
        print(f"Pass 1 alone (~${total_cost:.3f}) already hits --max-cost-usd "
              f"({args.max_cost_usd}) — stopping before any page writes. "
              f"Re-run with a higher budget or a smaller --max-items.")
        return

    items_by_id = {str(i["id"]): i for i in ready_items}
    # slug -> (entity dict, [items]) ; new entities keyed by a temp "new:<title>" slug
    touched = {}
    for a in plan.get("assignments", []):
        item = items_by_id.get(str(a.get("item_id")))
        if item is None:
            continue
        for e in a.get("entities", []):
            kind = e.get("kind")
            if kind not in ENTITY_DIRS:
                continue
            if "slug" in e:
                key = (kind, e["slug"])
                entity = next((x for x in entity_index if x["kind"] == kind and x["slug"] == e["slug"]), None)
                if entity is None:
                    continue
            elif "new_title" in e:
                slug = re.sub(r"[^a-z0-9]+", "-", e["new_title"].lower()).strip("-")
                key = (kind, slug)
                entity = {"kind": kind, "slug": slug, "title": e["new_title"], "gist": ""}
            else:
                continue
            touched.setdefault(key, (entity, []))[1].append(item)

    print(f"Entities touched this run: {len(touched)}")

    applied_paths, new_pages_for_index, skipped_for_budget = [], [], 0
    for (kind, slug), (entity, items_for_entity) in touched.items():
        if total_cost >= args.max_cost_usd:
            skipped_for_budget += 1
            continue
        path = ENTITY_DIRS[kind] / f"{slug}.md"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        content, cost = run_pass2(entity, items_for_entity, existing)
        total_cost += cost
        if content is None:
            continue
        if not is_path_allowed(path):
            print(f"  [REJECTED] outside allowlist: {path}", file=sys.stderr)
            continue
        if args.dry_run:
            print(f"  [dry-run] would write {path.relative_to(WIKI_ROOT)} ({len(content)} chars)")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        applied_paths.append(str(path.relative_to(WIKI_ROOT)))
        if not existing:
            fm, _ = parse_frontmatter(content)
            new_pages_for_index.append((kind, slug, fm.get("title", slug)))

    today = datetime.now(timezone.utc).date()
    log_entry = (
        f"\n## [{today}] synthesis | automated daily run\n"
        f"Processed {len(ready_items)} new item(s) "
        f"({', '.join(sorted({source_label(str(i['id'])) for i in ready_items}))}); "
        f"touched {len(applied_paths)} page(s): {', '.join(applied_paths) or '(none)'}. "
        f"Est. cost ~${total_cost:.3f}."
        + (f" {deferred} item(s) deferred to next run (--max-items)." if deferred else "")
        + (f" {len(not_ready)} item(s) awaiting build.mjs." if not_ready else "")
        + (f" {skipped_for_budget} entit(y/ies) skipped, over --max-cost-usd." if skipped_for_budget else "")
        + "\n"
    )
    if args.dry_run:
        print(f"[dry-run] would append to log.md:\n{log_entry}")
    else:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(log_entry)

    if new_pages_for_index and not args.dry_run:
        lines = [f"- [[{slug}]] — {title} ({kind})" for kind, slug, title in new_pages_for_index]
        with open(INDEX_PATH, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(lines) + "\n")
    elif new_pages_for_index:
        print(f"[dry-run] would append {len(new_pages_for_index)} line(s) to index.md")

    newly_processed = processed_ids | {str(i["id"]) for i in ready_items}
    save_state(newly_processed, args.dry_run)
    print(f"\nDone. {len(applied_paths)} page(s) touched, "
          f"{len(newly_processed) - len(processed_ids)} item(s) marked processed.")


if __name__ == "__main__":
    main()
