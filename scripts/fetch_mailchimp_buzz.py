#!/usr/bin/env python3
"""
scripts/fetch_mailchimp_buzz.py — fetch Berkman Klein Buzz newsletter issues
from Mailchimp (the successor to the 2006-2015 Sympa mailing list imported by
import_buzz.py) and merge them into raw/archive.json as buzz_ items.

Mailchimp Marketing API v3 (https://mailchimp.com/developer/marketing/api/).
Auth is HTTP Basic with any username and the API key as password; the
datacenter subdomain (e.g. "us21") is the suffix after the last "-" in the
key itself, per Mailchimp's own docs — no separate config needed for that.

Two-step API use per issue:
  1. GET /campaigns  (list_id + status=sent) — cheap, paginated, gives
     subject/title/send_time/archive_url for every sent campaign in the Buzz
     audience.
  2. GET /campaigns/{id}/content — one call per campaign that looks like a
     Buzz issue (see TITLE_FILTER), returns plain_text/html body.

Unlike fetch_tagteam.py's early-stop-on-a-known-page, this walks every page
of /campaigns every run rather than stopping at the first fully-known page:
TITLE_FILTER means a page can be "nothing new to add" without meaning
"nothing older is new either" (older pages could still hold not-yet-seen
Buzz issues interleaved with other campaign types on the same list). List
pages are cheap enough that walking all of them daily is a non-issue; the
expensive content fetch only ever happens for genuinely new Buzz issues.

Item id scheme continues import_buzz.py's buzz_<YYYYMM>_<N> (Sympa era ran
through 2015-05; this picks up wherever Mailchimp's own history starts).
Dedup key is the Mailchimp campaign id, stored as "mailchimp:<id>" in the
item's email.message_id field (not an RFC822 Message-ID, but same field/shape
as the Sympa-era items so nothing downstream needs to special-case source).

Resumable like fetch_publications.py: each item is staged to
raw/.mailchimp-staging.json (atomic write) immediately after its content is
fetched, merged into archive.json only at the end.

Usage:
    export MAILCHIMP_API_KEY=...
    python3 scripts/fetch_mailchimp_buzz.py --list-audiences     # find LIST_ID
    python3 scripts/fetch_mailchimp_buzz.py --dry-run --limit 5  # small test
    python3 scripts/fetch_mailchimp_buzz.py                      # fetch + merge
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

# Berkman Klein Buzz audience — found via --list-audiences and hardcoded here
# the same way fetch_tagteam.py hardcodes HUB_ID=1176 (project config, not a
# secret). Override with --list-id for a one-off run against another audience.
LIST_ID = os.environ.get("MAILCHIMP_BUZZ_LIST_ID", "4782a3c945")

# The Berkman Klein Center List audience is used for far more than the Buzz
# (event announcements, student bulletins, one-off "thanks for attending"
# follow-ups) — those carry different privacy/sensitivity expectations than
# the public Buzz digest, so inclusion here needs to be conservative. Every
# real issue observed uses the *internal campaign title* "The Buzz: <date>"
# consistently (confirmed against the full account history); the public
# subject_line varies too much to be a safe filter (e.g. "AI relationships;
# secrets; chilling effects" — no literal "buzz"). Only ever match on title.
TITLE_FILTER = "the buzz"

WIKI_ROOT = Path(__file__).parent.parent
ARCHIVE_PATH = WIKI_ROOT / "raw" / "archive.json"
STAGING_PATH = WIKI_ROOT / "raw" / ".mailchimp-staging.json"

PAGE_SIZE = 1000     # Mailchimp's max per request; the whole account's history
                     # fits in one call today, but keep paging below for growth
MAX_PAGES = 50       # safety cap: 50,000 campaigns, far beyond any real account
RETRIES = 4
RETRY_BACKOFF = 5.0

USER_AGENT = (
    "BKC-Archive-Wiki-Bot/1.0 "
    "(+https://github.com/szgrune/bkc-archive-wiki; "
    "daily incremental sync of Berkman Klein Buzz issues from Mailchimp)"
)


def server_prefix(api_key):
    """The datacenter suffix (e.g. 'us21') is baked into the key itself."""
    if "-" not in api_key:
        print("MAILCHIMP_API_KEY doesn't look like a Mailchimp key "
              "(expected a '-<dc>' suffix, e.g. '...-us21').", file=sys.stderr)
        sys.exit(1)
    return api_key.rsplit("-", 1)[1]


def make_session(api_key):
    session = requests.Session()
    session.auth = ("anystring", api_key)
    session.headers["User-Agent"] = USER_AGENT
    return session


def _get_with_retry(session, url, params=None):
    for attempt in range(1, RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=25)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} from Mailchimp", response=resp)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            if attempt == RETRIES:
                raise
            wait = RETRY_BACKOFF * (2 ** (attempt - 1))
            print(f"  [retry] {url} ({e.__class__.__name__}) — "
                  f"waiting {wait:.0f}s ({attempt}/{RETRIES})", file=sys.stderr)
            time.sleep(wait)


def list_audiences(session, base_url):
    resp = _get_with_retry(session, f"{base_url}/lists", {"count": 1000})
    for lst in resp.json().get("lists", []):
        print(f"  {lst['id']}  {lst['name']}  ({lst['stats']['member_count']} members)")


def fetch_campaign_page(session, base_url, list_id, offset):
    # sort by create_time, not send_time: confirmed against the real account
    # that send_time has enough ties to make offset-based paging unreliable
    # (the same campaign reappearing on multiple pages while others got
    # skipped entirely) — create_time, assigned once per campaign, doesn't.
    params = {
        "list_id": list_id,
        "status": "sent",
        "sort_field": "create_time",
        "sort_dir": "ASC",
        "count": PAGE_SIZE,
        "offset": offset,
        "fields": "campaigns.id,campaigns.web_id,campaigns.archive_url,"
                  "campaigns.send_time,campaigns.settings",
    }
    resp = _get_with_retry(session, f"{base_url}/campaigns", params)
    return resp.json().get("campaigns", [])


def matches_title_filter(campaign):
    if not TITLE_FILTER:
        return True
    title = campaign.get("settings", {}).get("title", "")
    return title.strip().lower().startswith(TITLE_FILTER.lower())


# ── body cleaning ─────────────────────────────────────────────────────────────
# Mailchimp's plain_text carries the same newsletter body as the Sympa-era
# emails did, plus a footer (social links, subscribe-preferences boilerplate,
# physical mailing address — this template doesn't use the "Copyright ©" /
# "Our mailing address is" wording those are usually guessed as) that also
# leaks unresolved *|MERGE_TAG|* placeholders (*|UNSUB|*, *|ARCHIVE|*, etc.)
# since the API returns the template source, not the as-sent/merged version.
# Confirmed via a real fetched issue that "You're getting this email because"
# reliably opens that block — cut there rather than line-filtering the way
# import_buzz.py's _is_boilerplate does, since it's one contiguous block.
_FOOTER_MARKERS = re.compile(
    r"\n\s*(?:You're getting this email because|Copyright \xa9|"
    r"Our mailing address is|unsubscribe from this list|"
    r"update (?:your )?subscription preferences)",
    re.IGNORECASE,
)

# Unresolved Mailchimp merge-tag placeholders (*|ARCHIVE|*, *|UNSUB|*, ...) —
# the API returns template source, not the as-sent/merged version. Confirmed
# these appear even in a 2016-era issue's "View this email in your browser
# (*|ARCHIVE|*)" line, well before the footer block, so strip them everywhere
# rather than assuming they're confined to the footer this cuts below.
_MERGE_TAG = re.compile(r"\(?\*\|[A-Z_]+\|\*\)?")

# Zero-width characters used as invisible inbox-preview-text padding — some
# issues (confirmed 2022+) open with a *|MC_PREVIEW_TEXT|* merge tag followed
# by hundreds of U+200C separated by spaces, purely to control how the email
# previews in an inbox before it's opened. Not content; strip everywhere.
_ZERO_WIDTH = re.compile("[​‌‍﻿]")

# Excerpt-only filters (content keeps the raw body, minus the footer, as-is —
# same as import_buzz.py). The plain-text conversion front-loads a couple of
# header/hero-image link lines and a bare date before the real first
# headline; skip those so the excerpt starts on actual newsletter content.
# Date format varies by era: "30 July 2026" (day-month-year, current
# template) vs "July 7 2016" (month-day-year, 2016 template) — match both.
_BARE_URL_LINE = re.compile(r"^https?://\S+$")
_BARE_DATE_LINE = re.compile(
    r"^(?:\d{1,2} \w+ \d{4}|\w+ \d{1,2},? \d{4})$"
)
_SEPARATOR_LINE = re.compile(r"^-{5,}$")


def clean_body(plain_text, html):
    text = plain_text or ""
    if not text.strip() and html:
        text = BeautifulSoup(html, "html.parser").get_text("\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MERGE_TAG.sub("", text)
    text = _ZERO_WIDTH.sub("", text)
    text = text.strip()

    m = _FOOTER_MARKERS.search(text)
    if m:
        text = text[:m.start()].strip()

    excerpt_lines = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or _BARE_URL_LINE.match(s) or _BARE_DATE_LINE.match(s) or _SEPARATOR_LINE.match(s):
            continue
        excerpt_lines.append(s)
        if len(excerpt_lines) >= 4:
            break
    excerpt_html = "\n".join(f"<p>{l}</p>" for l in excerpt_lines)
    return text, excerpt_html


def fetch_content(session, base_url, campaign_id):
    resp = _get_with_retry(session, f"{base_url}/campaigns/{campaign_id}/content")
    data = resp.json()
    return clean_body(data.get("plain_text"), data.get("html"))


def build_item(campaign, full_text, excerpt_html):
    settings = campaign.get("settings", {})
    send_time = campaign.get("send_time", "")
    year_month = send_time[:7].replace("-", "") if send_time else "unknown"

    return {
        "id": None,  # assigned after grouping by month — see assign_ids()
        "title": settings.get("subject_line") or settings.get("title") or
                 f"Berkman Klein Buzz {send_time[:7]}",
        "url": campaign.get("archive_url", ""),
        "guid": f"mailchimp:{campaign['id']}",
        "authors": settings.get("from_name") or "Berkman Klein Buzz",
        "date_published": send_time,
        "last_updated": send_time,
        "tags": ["berkman-buzz"],
        "description": excerpt_html,
        "content": full_text,
        "email": {
            "message_id": f"mailchimp:{campaign['id']}",
            "from": settings.get("from_name", ""),
            "list": "Berkman Klein Buzz (Mailchimp)",
            "source_file": campaign.get("archive_url", ""),
        },
        "_year_month": year_month,
    }


def assign_ids(new_items, existing_ids):
    """Fill in buzz_<YYYYMM>_<N>, continuing per-month numbering from
    whatever's already in the archive (Sympa-era or previously fetched)."""
    max_n = {}
    for id_ in existing_ids:
        m = re.match(r"^buzz_(\d{6})_(\d+)$", str(id_))
        if m:
            ym, n = m.group(1), int(m.group(2))
            max_n[ym] = max(max_n.get(ym, 0), n)

    for item in sorted(new_items, key=lambda x: x.get("date_published") or ""):
        ym = item.pop("_year_month")
        n = max_n.get(ym, 0) + 1
        max_n[ym] = n
        item["id"] = f"buzz_{ym}_{n}"


def atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    ap.add_argument("--limit", type=int, default=None,
                     help="Cap on number of new issues to fetch content for")
    ap.add_argument("--list-id", default=LIST_ID,
                     help="Mailchimp audience id (default: MAILCHIMP_BUZZ_LIST_ID env / LIST_ID const)")
    ap.add_argument("--list-audiences", action="store_true",
                     help="Print every Mailchimp audience (id + name) and exit — use this to find --list-id")
    args = ap.parse_args()

    api_key = os.environ.get("MAILCHIMP_API_KEY", "")
    if not api_key:
        print("MAILCHIMP_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    base_url = f"https://{server_prefix(api_key)}.api.mailchimp.com/3.0"
    session = make_session(api_key)

    if args.list_audiences:
        list_audiences(session, base_url)
        return

    if not args.list_id:
        print("No --list-id given and MAILCHIMP_BUZZ_LIST_ID / LIST_ID unset.\n"
              "Run with --list-audiences to find the Berkman Klein Buzz audience id.",
              file=sys.stderr)
        sys.exit(1)

    archive = json.loads(ARCHIVE_PATH.read_text()) if ARCHIVE_PATH.exists() else {"items": []}
    existing_ids = {str(i["id"]) for i in archive["items"]}
    existing_guids = {
        str(i["email"]["message_id"]) for i in archive["items"]
        if isinstance(i.get("email"), dict) and i["email"].get("message_id")
    }
    print(f"Archive: {len(archive['items'])} items ({len(existing_guids)} with an email guid)")

    staging = json.loads(STAGING_PATH.read_text()) if STAGING_PATH.exists() else []
    if staging:
        print(f"Resuming: {len(staging)} item(s) already staged from an interrupted run.")
        existing_guids |= {i["email"]["message_id"] for i in staging}

    # ── page through /campaigns, collecting ones that look like Buzz issues ──
    # seen_ids guards against duplicate rows across pages regardless of sort
    # stability — cheap insurance on top of sorting by create_time (see
    # fetch_campaign_page's comment for why send_time wasn't safe to page on).
    candidates = []
    seen_ids = set()
    for page in range(MAX_PAGES):
        offset = page * PAGE_SIZE
        campaigns = fetch_campaign_page(session, base_url, args.list_id, offset)
        if not campaigns:
            print(f"offset {offset}: empty — reached the end of the audience's sent campaigns.")
            break

        page_new = [
            c for c in campaigns
            if c["id"] not in seen_ids and matches_title_filter(c)
            and f"mailchimp:{c['id']}" not in existing_guids
        ]
        seen_ids.update(c["id"] for c in campaigns)
        print(f"offset {offset}: {len(campaigns)} campaigns, {len(page_new)} new Buzz issues")
        candidates.extend(page_new)
    else:
        print(f"\nHit MAX_PAGES={MAX_PAGES} safety cap — there may be more history than "
              f"usual. Re-run to continue (already-merged issues are skipped).")

    if args.limit:
        candidates = candidates[:args.limit]
        print(f"Capped at --limit {args.limit}.")

    print(f"\nFetching content for {len(candidates)} new issue(s)...")

    for campaign in candidates:
        full_text, excerpt_html = fetch_content(session, base_url, campaign["id"])
        item = build_item(campaign, full_text, excerpt_html)
        staging.append(item)
        atomic_write(STAGING_PATH, json.dumps(staging, indent=2, ensure_ascii=False))
        print(f"  staged  {campaign['send_time'][:10]}  "
              f"{campaign['settings'].get('subject_line', '')[:60]}")

    print(f"\n{len(staging)} new item(s) staged "
          f"({len(staging) - len(candidates)} carried over from a prior interrupted run).")

    if args.dry_run or not staging:
        if not staging:
            print("Nothing to merge.")
        else:
            print("(--dry-run: staging file kept for inspection, archive.json not touched)")
        return

    assign_ids(staging, existing_ids)

    combined = staging + archive["items"]
    combined.sort(key=lambda x: x.get("date_published") or "", reverse=True)
    archive["items"] = combined
    archive["item_count"] = len(combined)

    ARCHIVE_PATH.write_text(json.dumps(archive, indent=2, ensure_ascii=False))
    STAGING_PATH.unlink(missing_ok=True)
    print(f"archive.json → {len(combined)} total items")


if __name__ == "__main__":
    main()
