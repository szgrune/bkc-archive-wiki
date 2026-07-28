#!/usr/bin/env python3
"""
scripts/fetch_publications.py — fetch BKC-affiliated publications into
raw/archive.json, via BKC's own publications index
(https://cyber.harvard.edu/publications), not by scraping SSRN directly.

Why not SSRN directly: there's no single SSRN eJournal aggregating BKC's
output (papers just carry a "Berkman Klein Center Research Publication No."
label individually — nothing to follow), and SSRN itself sends explicit
anti-automation signals: robots.txt blocks GPTBot/ChatGPT-User/Google-Extended
by name, a direct request gets Cloudflare's bot-challenge block, and the
response carries a `tdm-reservation: 1` header pointing at Elsevier's formal
Text-and-Data-Mining opt-out policy. Unlike TagTeam or this website (BKC's
own tools), SSRN is a third-party commercial platform with no institutional
relationship giving standing here — so this script never touches SSRN.

Instead: cyber.harvard.edu/publications is BKC's own curated, paginated,
reverse-chronological index. robots.txt doesn't restrict it. Each detail
page already shows an abstract, authors (linked to BKC profile pages), a
date, topic tags, and BKC's own outbound link to wherever the paper actually
lives (SSRN, DASH, etc.) — so "links to SSRN" happens naturally, via BKC's
own citation, without ever scraping SSRN's site.

Item id: pub_<year>-<slug> derived from BKC's own URL path (matches the
existing convention of deriving ids from the source's natural identifier,
same as buzz_YYYYMM_N / yt_VIDEO_ID). `content` is the full abstract text —
BKC's own published summary, not the paper itself.

Incremental, same pattern as fetch_tagteam.py: listing is reverse-
chronological; stop once a full page has nothing new. Exception: the very
first run has nothing to stop at (0 pub_ items exist yet) and walks the
full history in one go — BKC's publications page goes back to 1993; the
first real run merged 330 items. Not capped, since there's no hard quota
(unlike YouTube's Data API).

Three URL schemes appear across BKC's history and are all handled by
derive_id() and the listing selector: /publication/<year>/<slug> (current),
/publications/<year>[/<mm>]/<slug> (old, plural), and bare /node/<nid> for
the oldest content with no slug alias. Matching only the current scheme
made older pages look like they had nothing new (0 recognized links, even
though the page had entries) and falsely tripped the stop-early logic
partway through history — a real bug caught during initial testing, not a
hypothetical.

Resumable: each item is staged to raw/.publications-staging.json (atomic
write, gitignored) immediately after it's built, merged into archive.json
only at the end — a crash mid-run loses at most the one item in flight.
Worth having: testing surfaced that this site's connections go stale after
the per-request delay (nearly every request failed once before succeeding
on retry) until `Connection: close` was added to the session, which fixed
it outright (a fresh connection per request costs a handshake, far cheaper
than the 8s+ backoff a stale-connection reset was costing almost every
single request before this).

Dedup: skips a discovered publication if its own URL, OR any external link
found on its detail page (SSRN/DASH), already matches an existing
archive.json item's url (scheme-normalized — some existing entries were
captured years ago as http://, not https://) — several publications are
already present via incidental TagTeam bookmarking. Never modifies an
existing item, consistent with every other pipeline's append-only rule.

Politeness: robots.txt carries a `Crawl-delay: 15` (scoped to one block, but
applying it as the general rule is the safe read); retry+backoff on
failures; a descriptive User-Agent.

Usage:
    python3 scripts/fetch_publications.py --dry-run --limit 5
    python3 scripts/fetch_publications.py
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

WIKI_ROOT = Path(__file__).parent.parent
ARCHIVE_PATH = WIKI_ROOT / "raw" / "archive.json"
STAGING_PATH = WIKI_ROOT / "raw" / ".publications-staging.json"

BASE_URL = "https://cyber.harvard.edu"
LISTING_URL = f"{BASE_URL}/publications"

PAGE_DELAY = 3.0    # robots.txt Crawl-delay: 15 is scoped to one block, but
DETAIL_DELAY = 3.0  # applying it generally is the polite reading
RETRIES = 4
RETRY_BACKOFF = 8.0

USER_AGENT = (
    "BKC-Archive-Wiki-Bot/1.0 "
    "(+https://github.com/szgrune/bkc-archive-wiki; "
    "daily sync of BKC's own publications page; "
    "contact: repo owner via GitHub)"
)


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _get_with_retry(session, url, params=None):
    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                raise requests.exceptions.HTTPError("429 rate limited", response=resp)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            if attempt == RETRIES:
                raise
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            print(f"  [retry] {url} ({e.__class__.__name__}) — "
                  f"waiting {wait:.0f}s ({attempt}/{RETRIES})", file=sys.stderr)
            time.sleep(wait)


def derive_id(url):
    """BKC's publications listing mixes three URL schemes across its history:
    /publication/<year>/<slug> (current), /publications/<year>[/<mm>]/<slug>
    (old, plural — some already in archive.json via TagTeam under this
    scheme), and bare /node/<nid> for the oldest content with no slug alias
    at all. Handle all three so nothing gets silently dropped."""
    m = re.search(r"/publications?/(.+)$", url)
    if m:
        segments = [s for s in m.group(1).strip("/").split("/") if s]
        if segments and re.match(r"^\d{4}$", segments[0]):
            year, slug_parts = segments[0], segments[1:]
        else:
            year, slug_parts = "0000", segments
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", "-".join(slug_parts) or "untitled").strip("-").lower()
        return f"pub_{year}-{slug}"
    m = re.search(r"/node/(\d+)", url)
    if m:
        return f"pub_node-{m.group(1)}"
    return f"pub_{re.sub(r'[^a-zA-Z0-9]+', '-', url).strip('-').lower()}"


def normalize_url(url):
    """Scheme/trailing-slash/case-insensitive-host key for dedup — some items
    already in archive.json were captured years ago as http://, not https://."""
    if not url:
        return ""
    u = re.sub(r"^https?://", "", url.strip(), flags=re.IGNORECASE).rstrip("/")
    return u.lower()


# ── listing ──────────────────────────────────────────────────────────────────

def collect_new_listing_entries(session, existing_ids, existing_urls, limit=None):
    new_entries = []
    page = 0
    while True:
        resp = _get_with_retry(session, LISTING_URL, {"page": page})
        soup = BeautifulSoup(resp.text, "html.parser")
        blocks = soup.select("div.c-unique-item")
        if not blocks:
            print(f"page {page}: empty — reached the end of the listing.")
            break

        page_entries = []
        for block in blocks:
            # Older entries use /publications/<year>/... (plural) or a bare
            # /node/<nid> with no slug alias at all — match any of the three
            # schemes rather than just the current /publication/<year>/<slug>
            # one, or older pages silently look "empty" and falsely trip the
            # stop-on-nothing-new logic.
            a = block.select_one(
                "a[href^='/publication/'], a[href^='/publications/'], a[href^='/node/']"
            )
            if not a:
                continue
            title_el = block.select_one("h2.c-grid-block__heading")
            page_entries.append({
                "url": BASE_URL + a["href"],
                "title": title_el.get_text(strip=True) if title_el else "",
            })

        page_new = [
            e for e in page_entries
            if derive_id(e["url"]) not in existing_ids
            and normalize_url(e["url"]) not in existing_urls
        ]
        print(f"page {page}: {len(page_entries)} entries, {len(page_new)} new")
        new_entries.extend(page_new)

        if not page_new:
            print("Full page with nothing new — stopping (rest is already archived).")
            break
        if limit and len(new_entries) >= limit:
            new_entries = new_entries[:limit]
            print(f"Capped at --limit {limit}.")
            break

        page += 1
        time.sleep(PAGE_DELAY)

    return new_entries


# ── detail page ──────────────────────────────────────────────────────────────

def fetch_detail(session, url):
    resp = _get_with_retry(session, url)
    soup = BeautifulSoup(resp.text, "html.parser")

    title_el = soup.select_one("h1.c-detail-header__title")
    time_el = soup.select_one(".c-detail-header__date time")
    date_iso = time_el["datetime"] if time_el and time_el.has_attr("datetime") else None

    authors = []
    for a in soup.select("a.c-byline__content-link"):
        name_el = a.select_one(".c-byline__name")
        name = name_el.get_text(strip=True) if name_el else a.get_text(strip=True)
        href = a.get("href", "")
        authors.append({
            "name": name,
            "bkc_profile_url": BASE_URL + href if href.startswith("/") else href,
        })

    topics = [t.get_text(strip=True) for t in soup.select(".c-detail-header__tags a.o-tag")]

    abstract_parts, saw_label = [], False
    body = soup.select_one("div.c-detail__body")
    if body:
        for p in body.find_all("p", recursive=False):
            text = p.get_text(strip=True)
            if text.upper() == "ABSTRACT":
                saw_label = True
                continue
            if text:
                abstract_parts.append(text)
    abstract = "\n\n".join(abstract_parts)

    external_links = {}
    for a in soup.select("a.c-anchor-nav__link"):
        href = a.get("href", "")
        if "ssrn.com" in href:
            external_links["ssrn"] = href
        elif "dash.harvard.edu" in href:
            external_links["dash"] = href
        elif href.startswith("http") and BASE_URL not in href:
            external_links.setdefault("other", href)

    return {
        "title": title_el.get_text(strip=True) if title_el else "",
        "date_iso": date_iso,
        "authors": authors,
        "topics": topics,
        "abstract": abstract,
        "external_links": external_links,
    }


def to_html_description(text, limit=500):
    if not text:
        return ""
    snippet = text[:limit].rsplit(" ", 1)[0] if len(text) > limit else text
    return f"<p>{snippet}</p>"


def build_item(entry, detail):
    date_iso = detail["date_iso"] or ""
    date_published = f"{date_iso}T00:00:00.000-05:00" if date_iso else ""
    return {
        "id": derive_id(entry["url"]),
        "title": detail["title"] or entry["title"],
        "url": entry["url"],
        "guid": None,
        "authors": ", ".join(a["name"] for a in detail["authors"]) or None,
        "date_published": date_published,
        "last_updated": date_published,
        "tags": ["bkc-publication"],
        "description": to_html_description(detail["abstract"]),
        "content": detail["abstract"],
        "publication": {
            "topics": detail["topics"],
            "external_links": detail["external_links"],
            "authors_profiles": detail["authors"],
        },
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    ap.add_argument("--limit", type=int, default=None,
                     help="Cap on number of new publications to process (for testing)")
    args = ap.parse_args()

    archive = json.loads(ARCHIVE_PATH.read_text()) if ARCHIVE_PATH.exists() else {"items": []}
    existing_ids = {str(i["id"]) for i in archive["items"]}
    existing_urls = {normalize_url(i["url"]) for i in archive["items"] if i.get("url")}

    staging = json.loads(STAGING_PATH.read_text()) if STAGING_PATH.exists() else []
    if staging:
        print(f"Resuming: {len(staging)} item(s) already staged from an interrupted run.")
        existing_ids |= {str(i["id"]) for i in staging}
        existing_urls |= {normalize_url(i["url"]) for i in staging if i.get("url")}

    print(f"Archive: {len(archive['items'])} items ({len(existing_urls)} with a url)")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    # Every request was hitting a connection reset on its first attempt during
    # testing (recovering on retry) — consistent with a stale keep-alive
    # connection going bad during the delay between requests. Disabling
    # keep-alive costs a fresh TCP handshake per request but avoids paying a
    # full retry backoff (8s+) for something a plain new connection avoids.
    session.headers["Connection"] = "close"

    new_entries = collect_new_listing_entries(session, existing_ids, existing_urls, args.limit)
    print(f"\n{len(new_entries)} new publication(s) to fetch details for.")

    skipped_dup = 0
    for i, entry in enumerate(new_entries):
        print(f"[{i + 1}/{len(new_entries)}] {entry['title'][:60]}")
        detail = fetch_detail(session, entry["url"])
        time.sleep(DETAIL_DELAY)

        ext_urls = {normalize_url(u) for u in detail["external_links"].values()}
        if ext_urls & existing_urls:
            print("  already covered via an external link already in archive.json — skipping")
            skipped_dup += 1
            continue

        item = build_item(entry, detail)
        if args.dry_run:
            print(f"  [dry-run] {item['id']}  {item['date_published'][:10]}  {item['title'][:60]}")
            continue

        # Write immediately — a crash mid-run (this site's connections have
        # been flaky) loses at most the one item in flight, not the whole run.
        staging.append(item)
        atomic_write(STAGING_PATH, json.dumps(staging, indent=2, ensure_ascii=False))

    print(f"\n{len(staging)} new item(s) staged "
          f"({skipped_dup} skipped as already-covered via an external link).")

    if args.dry_run or not staging:
        if not staging:
            print("Nothing to merge.")
        return

    combined = staging + archive["items"]
    combined.sort(key=lambda x: x.get("date_published") or "", reverse=True)
    archive["items"] = combined
    archive["item_count"] = len(combined)

    ARCHIVE_PATH.write_text(json.dumps(archive, indent=2, ensure_ascii=False))
    STAGING_PATH.unlink(missing_ok=True)
    print(f"archive.json → {len(combined)} total items")


if __name__ == "__main__":
    main()
