#!/usr/bin/env python3
"""
scripts/fetch_tagteam.py — incrementally fetch new items from BKC's TagTeam
hub 1176 (https://tagteam.harvard.edu/hubs/1176) and merge them into
raw/archive.json.

TagTeam is Berkman Klein Center's own open-source tagging tool
(github.com/berkmancenter/tagteam) — hub 1176 is BKC's own curated feed, and
the JSON/RSS/Atom endpoints used here are the hub's own documented "Export"
feature (visible in its UI), not a third-party or undocumented API. Note:
robots.txt nominally disallows /hubs/*/items.json et al. for all crawlers —
a common pattern for feed URLs aimed at stopping search-engine indexing of
dynamically-generated feed content, not at the feed-reader-style polling
these formats exist for. Treated here as legitimate given BKC owns both the
tool and the hub, but polled politely: once daily, a descriptive User-Agent,
and incremental (never re-walks the full multi-thousand-item history).

Two calls per page, merged by URL:
  - items.json: structured fields (id, url, tags, dates) — no description.
  - items.rss:  same order/count as items.json for matching page/per_page,
                carries a plain-text <description> when present.

Incremental strategy: items are returned in date_published-descending order.
Page through until a full page comes back with zero items not already in
archive.json (by id), then stop. Known limitation: an old article tagged
into the hub *today* (backdated date_published) sorts by its old date, not
today, so could in principle sit past this stopping point and be missed —
mitigated by the periodic full re-scrapes described in AGENTS.md's Ingest
workflow, which remain the full safety net. In practice BKC's curators tag
things at or near publish time, so this is rare.

Usage:
    python3 scripts/fetch_tagteam.py --dry-run     # report only, no writes
    python3 scripts/fetch_tagteam.py               # fetch + merge new items
"""

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

HUB_ID = 1176
BASE_URL = f"https://tagteam.harvard.edu/hubs/{HUB_ID}/items"
ARCHIVE_PATH = Path(__file__).parent.parent / "raw" / "archive.json"

PER_PAGE = 100
PAGE_DELAY = 2.0     # seconds between page requests — be a good citizen
MAX_PAGES = 30       # safety cap (30 * 100 = 3,000 items checked per run,
                     # far more than a daily incremental gap should ever need)
RETRIES = 4
RETRY_BACKOFF = 8.0  # base seconds; doubles each attempt (confirmed the site
                     # does rate-limit — a burst of exploratory requests
                     # while building this script tripped a real 429)

USER_AGENT = (
    "BKC-Archive-Wiki-Bot/1.0 "
    "(+https://github.com/szgrune/bkc-archive-wiki; "
    "daily incremental sync of hub 1176's own Export feed; "
    "contact: repo owner via GitHub)"
)


def _get_with_retry(session, url, params):
    """GET with retry+backoff on 429/connection errors — confirmed this site
    rate-limits, so transient failures are expected under any real load."""
    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=25)
            if resp.status_code == 429:
                raise requests.exceptions.HTTPError("429 rate limited", response=resp)
            resp.raise_for_status()
            return resp
        except (requests.exceptions.RequestException,) as e:
            if attempt == RETRIES:
                raise
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            print(f"  [retry] {url} ({e.__class__.__name__}) — "
                  f"waiting {wait:.0f}s ({attempt}/{RETRIES})", file=sys.stderr)
            time.sleep(wait)


def fetch_json_page(session, page):
    resp = _get_with_retry(session, BASE_URL + ".json",
                            {"page": page, "per_page": PER_PAGE})
    return resp.json().get("feed_items", [])


def fetch_rss_descriptions(session, page):
    """Return {url: description_text} for one page of the RSS export."""
    resp = _get_with_retry(session, BASE_URL + ".rss",
                            {"page": page, "per_page": PER_PAGE})
    root = ET.fromstring(resp.text)
    out = {}
    for item in root.iter("item"):
        link = item.findtext("link")
        desc = item.findtext("description")
        if link and desc:
            out[link.strip()] = desc.strip()
    return out


def to_html_description(text):
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    return f"<p>{normalized}</p>" if normalized else ""


def build_archive_item(json_item, descriptions):
    tags = (json_item.get("tags") or {}).get(f"hub_{HUB_ID}", [])
    desc_text = descriptions.get(json_item.get("url", ""), "")
    return {
        "id":             json_item["id"],
        "title":          json_item.get("title", ""),
        "url":            json_item.get("url", ""),
        "guid":           json_item.get("guid"),
        "authors":        json_item.get("authors"),
        "date_published": json_item.get("date_published", ""),
        "last_updated":   json_item.get("last_updated", ""),
        "tags":           tags,
        "description":    to_html_description(desc_text),
        "content":        "",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                     help="Report what would be merged, no writes")
    args = ap.parse_args()

    archive = json.loads(ARCHIVE_PATH.read_text()) if ARCHIVE_PATH.exists() else {"items": []}
    existing_ids = {i["id"] for i in archive["items"] if isinstance(i.get("id"), int)}
    print(f"Archive: {len(archive['items'])} items ({len(existing_ids)} numeric TagTeam ids)")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    new_items = []
    for page in range(1, MAX_PAGES + 1):
        json_items = fetch_json_page(session, page)
        if not json_items:
            print(f"page {page}: empty — reached the end of the hub.")
            break

        time.sleep(PAGE_DELAY)
        descriptions = fetch_rss_descriptions(session, page)

        page_new = [ji for ji in json_items if ji["id"] not in existing_ids]
        print(f"page {page}: {len(json_items)} items, {len(page_new)} new")

        new_items.extend(build_archive_item(ji, descriptions) for ji in page_new)

        if not page_new:
            print("Full page with nothing new — stopping (rest is already archived).")
            break

        time.sleep(PAGE_DELAY)
    else:
        print(f"\nHit MAX_PAGES={MAX_PAGES} safety cap without finding an all-known "
              f"page — there may be more new items than usual. Re-run to continue "
              f"(already-merged ids are skipped), or investigate before assuming "
              f"this covered everything.")

    print(f"\nTotal new items found: {len(new_items)}")

    if args.dry_run:
        for item in new_items[:20]:
            print(f"  {item['id']}  {item['date_published'][:10]}  {item['title'][:60]}")
        if len(new_items) > 20:
            print(f"  … and {len(new_items) - 20} more")
        return

    if not new_items:
        print("Nothing new to merge.")
        return

    combined = new_items + archive["items"]
    combined.sort(key=lambda x: x.get("date_published") or "", reverse=True)
    archive["items"] = combined
    archive["item_count"] = len(combined)

    ARCHIVE_PATH.write_text(json.dumps(archive, indent=2, ensure_ascii=False))
    print(f"archive.json → {len(combined)} total items")


if __name__ == "__main__":
    main()
