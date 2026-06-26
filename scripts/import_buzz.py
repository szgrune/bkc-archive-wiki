#!/usr/bin/env python3
"""
scripts/import_buzz.py — parse Berkman Buzz .eml archive and merge into archive.json

Usage:
    python3 scripts/import_buzz.py /path/to/berkman-buzz.zip
    python3 scripts/import_buzz.py /path/to/berkman-buzz.zip --dry-run

Each .eml becomes one archive item (the newsletter issue itself, not individual links).
Items are tagged "berkman-buzz" and carry an "email" sub-object with metadata.
Deduplicates by Message-ID across the two list addresses.
"""

import json
import re
import sys
import zipfile
import argparse
from pathlib import Path
from email import message_from_bytes, policy as epolicy
from email.utils import parseaddr, parsedate_to_datetime

ARCHIVE_PATH = Path(__file__).parent.parent / "raw" / "archive.json"


# ── date normalization ────────────────────────────────────────────────────────

def parse_email_date(date_str):
    """RFC 2822 date → 'YYYY-MM-DDTHH:MM:SS.000±HH:MM' string, or ''."""
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        # Format to match TagTeam convention
        offset = dt.strftime("%z")           # e.g. "-0400"
        offset_fmt = offset[:3] + ":" + offset[3:]   # "-04:00"
        return dt.strftime(f"%Y-%m-%dT%H:%M:%S.000{offset_fmt}")
    except Exception:
        return ""


# ── body cleaning ─────────────────────────────────────────────────────────────

_LINK_RE = re.compile(r"<https?://[^>]+>")

# Lines matching any of these patterns are boilerplate to skip when building
# the excerpt.  Covers both the 2006 plain-text format and the later HTML-lite
# multipart format.
_BOILERPLATE_PATTERNS = [
    re.compile(r"BERKMAN BUZZ", re.IGNORECASE),
    re.compile(r"Berkman (?:Center for Internet|Klein Center)", re.IGNORECASE),
    re.compile(r"^Week of\b", re.IGNORECASE),
    re.compile(r"subscribe|unsubscribe|sign.?up", re.IGNORECASE),
    re.compile(r"Browse online", re.IGNORECASE),
    re.compile(r"iTunes|Facebook|Twitter|Flickr|YouTube\s*<", re.IGNORECASE),
    re.compile(r"RSS\s*<http", re.IGNORECASE),
    re.compile(r"(?:selected weekly|past week'?s? online)", re.IGNORECASE),
    re.compile(r"passed you the Buzz", re.IGNORECASE),
    re.compile(r"^What.{0,3}s going on", re.IGNORECASE),
    re.compile(r"take your pick here", re.IGNORECASE),
    re.compile(r"Harvard Law School", re.IGNORECASE),
    re.compile(r"^RSS\s*$"),
    re.compile(r"^Quote\s*$", re.IGNORECASE),
    re.compile(r"^Quotation mark\s*$", re.IGNORECASE),
    re.compile(r"from around the Berkman", re.IGNORECASE),
    re.compile(r"people and projects", re.IGNORECASE),
    re.compile(r"^<https?://[^>]+>$"),   # bare URL line
    re.compile(r"^\*\s*$"),              # lone asterisk (2006 format divider)
]


def _is_boilerplate(line):
    s = line.strip()
    if not s:
        return True
    # Check raw line against patterns
    for pat in _BOILERPLATE_PATTERNS:
        if pat.search(s):
            return True
    # Strip inline URLs and re-check (catches e.g. "<url> RSS")
    stripped = _LINK_RE.sub("", s).strip()
    if not stripped:
        return True
    for pat in _BOILERPLATE_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def clean_body(text):
    """Return (full_text, excerpt_html) for a plain-text email body."""
    if not text:
        return "", ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Build excerpt: first 4 non-boilerplate lines, inline URLs stripped
    excerpt_lines = []
    for line in text.split("\n"):
        if _is_boilerplate(line):
            continue
        display = _LINK_RE.sub("", line).strip().lstrip("*•·- \t")
        if not display:
            continue
        excerpt_lines.append(display)
        if len(excerpt_lines) >= 4:
            break

    desc_html = "\n".join(f"<p>{l}</p>" for l in excerpt_lines)
    return text, desc_html


# ── URL extraction ────────────────────────────────────────────────────────────

_ONLINE_URL_RE = re.compile(
    r"Browse online(?:\s+here)?\s*\n?\s*<(https?://[^>]+)>",
    re.IGNORECASE,
)
_VIEW_ONLINE_RE = re.compile(
    r"[Vv]iew (?:this email )?(?:in|on) (?:your )?browser[^\n]*<(https?://[^>]+)>",
    re.IGNORECASE,
)


def extract_online_url(body_text):
    """Return the 'browse online' canonical URL from the body, or None."""
    for pattern in (_ONLINE_URL_RE, _VIEW_ONLINE_RE):
        m = pattern.search(body_text)
        if m:
            return m.group(1).strip()
    return None


# ── item builder ──────────────────────────────────────────────────────────────

def synthetic_url(year_month, n):
    """Fallback URL when no online link is present."""
    return f"https://cyber.law.harvard.edu/berkman-buzz/{year_month}/{n}"


def build_item(zip_path, msg, list_addr, year_month, n):
    """
    zip_path  : e.g. 'berkman-buzz-and-press-list@eon.law.harvard.edu/2006-07/1.eml'
    msg       : email.message object
    list_addr : e.g. 'berkman-buzz-and-press-list@eon.law.harvard.edu'
    year_month: e.g. '2006-07'
    n         : e.g. '1'
    """
    subject    = msg.get("subject", "").strip()
    date_raw   = msg.get("date", "")
    from_raw   = msg.get("from", "")
    message_id = msg.get("message-id", "").strip()

    display_name, from_addr = parseaddr(from_raw)
    authors = display_name.strip() or from_addr.strip() or "Berkman Buzz"

    date_iso = parse_email_date(date_raw)
    item_id  = f"buzz_{year_month.replace('-', '')}_{n}"

    # Get plain-text body
    try:
        body_part = msg.get_body(preferencelist=("plain",))
        raw_body  = body_part.get_content() if body_part else ""
    except Exception:
        raw_body = ""

    full_text, desc_html = clean_body(raw_body)
    url = extract_online_url(full_text) or synthetic_url(year_month, n)

    return {
        "id":             item_id,
        "title":          subject or f"Berkman Buzz {year_month}",
        "url":            url,
        "guid":           message_id,
        "authors":        authors,
        "date_published": date_iso,
        "last_updated":   date_iso,
        "tags":           ["berkman-buzz"],
        "description":    desc_html,
        "content":        full_text,
        "email": {
            "message_id":  message_id,
            "from":        from_raw.strip(),
            "list":        list_addr,
            "source_file": zip_path,
        },
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Import Berkman Buzz .eml archive into raw/archive.json"
    )
    ap.add_argument("zip_path", help="Path to berkman-buzz.zip")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and report, no writes")
    args = ap.parse_args()

    zip_path = Path(args.zip_path)
    if not zip_path.exists():
        print(f"File not found: {zip_path}", file=sys.stderr)
        sys.exit(1)

    # Load existing archive
    archive = json.loads(ARCHIVE_PATH.read_text())
    existing_ids   = {str(i["id"])   for i in archive["items"]}
    existing_guids = {str(i.get("guid") or "") for i in archive["items"]}

    print(f"Archive: {len(archive['items'])} items")

    # Parse emails from zip
    new_items    = []
    seen_msg_ids = set()   # deduplicate across the two list addresses
    skipped_dup  = 0
    parse_errors = 0

    # Path pattern: <list-addr>/<YYYY-MM>/<N>.eml
    PATH_RE = re.compile(
        r"^([^/]+)/(\d{4}-\d{2})/(\d+)\.eml$"
    )

    with zipfile.ZipFile(zip_path) as z:
        eml_files = sorted(n for n in z.namelist() if n.endswith(".eml"))
        print(f"Found {len(eml_files)} .eml files")

        for zip_name in eml_files:
            m = PATH_RE.match(zip_name)
            if not m:
                continue
            list_addr, year_month, n = m.groups()

            try:
                with z.open(zip_name) as f:
                    raw = f.read()
                msg = message_from_bytes(raw, policy=epolicy.default)
            except Exception as e:
                print(f"  [error] {zip_name}: {e}", file=sys.stderr)
                parse_errors += 1
                continue

            msg_id = (msg.get("message-id") or "").strip()

            # Deduplicate by Message-ID across both list addresses
            if msg_id and msg_id in seen_msg_ids:
                skipped_dup += 1
                continue
            if msg_id:
                seen_msg_ids.add(msg_id)

            item_id = f"buzz_{year_month.replace('-', '')}_{n}"

            # Skip if already in archive (by id or guid)
            if item_id in existing_ids or (msg_id and msg_id in existing_guids):
                skipped_dup += 1
                continue

            item = build_item(zip_name, msg, list_addr, year_month, n)
            new_items.append(item)

    print(f"New items: {len(new_items)}")
    print(f"Duplicates / already present: {skipped_dup}")
    if parse_errors:
        print(f"Parse errors: {parse_errors}")

    if args.dry_run:
        print("\nSample (first 3):")
        for item in new_items[:3]:
            it = dict(item)
            it["content"] = it["content"][:100] + "..." if it["content"] else ""
            it["email"] = item["email"]
            print(f"  {it['id']}  {it['date_published'][:10]}  {it['title'][:60]}")
            print(f"    url: {it['url']}")
            print(f"    authors: {it['authors']}")
            print(f"    desc: {it['description'][:80]}")
        return

    if not new_items:
        print("Nothing to merge.")
        return

    # Merge and sort
    combined = new_items + archive["items"]
    combined.sort(key=lambda x: x.get("date_published") or "", reverse=True)

    archive["items"]      = combined
    archive["item_count"] = len(combined)

    ARCHIVE_PATH.write_text(json.dumps(archive, indent=2, ensure_ascii=False))
    print(f"archive.json → {len(combined)} total items")


if __name__ == "__main__":
    main()
