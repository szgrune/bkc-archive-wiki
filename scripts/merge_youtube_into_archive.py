#!/usr/bin/env python3
"""
scripts/merge_youtube_into_archive.py — fold collection/json/youtube.json into
raw/archive.json, so YouTube videos get item stubs via build.mjs alongside
TagTeam bookmarks and Berkman Buzz newsletters.

Mirrors import_buzz.py's merge pattern (read source, skip ids already in
archive.json, merge + sort by date_published, write). Unlike import_buzz.py
(a one-time manual import of a static .eml zip), this script is meant to be
re-run repeatedly as fetch_youtube_api.py/fetch_youtube.py add new videos to
collection/json/youtube.json over time — every run only adds ids not yet in
archive.json, so it's safe to call daily from CI (see
.github/workflows/fetch-youtube-captions.yml) or by hand.

Each merged item mirrors the catalog entry's shape (id, title, url, guid,
authors, dates, tags, description, content, `youtube` block) unchanged —
`content` stays the short video description, NOT the full transcript.
Deliberately does not inline transcript text: unlike Buzz's newsletter body
(small, one email), a YouTube transcript can be tens of KB per video, and
archive.json is one shared 7,000+-item file — duplicating ~1,100 transcripts
into it would bloat it by tens of MB. The full text stays exactly where
fetch_youtube.py/fetch_youtube_api.py already put it, one file per video at
collection/txt/youtube/yt_<id>.txt; the merged item's `transcript.path` field
is the pointer to it (same role as Buzz's `email.source_file`).

Usage:
    python3 scripts/merge_youtube_into_archive.py
    python3 scripts/merge_youtube_into_archive.py --dry-run
"""

import argparse
import json
import sys

from youtube_common import ARCHIVE_PATH, CATALOG_PATH, load_catalog


def build_archive_item(entry):
    """Catalog entry (collection/json/youtube.json shape) → archive.json item.
    Currently a straight copy — kept as its own function so item shaping can
    diverge from the catalog shape later without touching the merge loop."""
    return dict(entry)


def main():
    ap = argparse.ArgumentParser(
        description="Merge collection/json/youtube.json into raw/archive.json"
    )
    ap.add_argument("--dry-run", action="store_true",
                     help="Report what would be merged, no writes")
    args = ap.parse_args()

    if not ARCHIVE_PATH.exists():
        sys.exit(f"archive.json not found at {ARCHIVE_PATH}")
    if not CATALOG_PATH.exists():
        print("youtube.json not found — nothing to merge.")
        return

    archive = json.loads(ARCHIVE_PATH.read_text())
    catalog = load_catalog()

    existing_ids = {str(i["id"]) for i in archive["items"]}
    existing_yt_urls = {
        i["url"] for i in archive["items"]
        if "youtube.com/watch" in i.get("url", "") or "youtu.be/" in i.get("url", "")
    }

    print(f"Archive: {len(archive['items'])} items  |  "
          f"YouTube catalog: {len(catalog['items'])} videos")

    new_items = [
        build_archive_item(entry)
        for entry in catalog["items"]
        if str(entry["id"]) not in existing_ids
        and entry.get("url") not in existing_yt_urls
    ]

    with_transcript = sum(1 for i in new_items if i.get("transcript", {}).get("available"))
    print(f"New to merge: {len(new_items)} ({with_transcript} with a transcript.path, "
          f"{len(new_items) - with_transcript} no captions yet)")

    if args.dry_run:
        for item in new_items[:15]:
            print(f"  {item['id']}  {(item.get('date_published') or '')[:10]}  "
                  f"{item['title'][:60]}")
        if len(new_items) > 15:
            print(f"  … and {len(new_items) - 15} more")
        return

    if not new_items:
        print("Nothing to merge.")
        return

    combined = new_items + archive["items"]
    combined.sort(key=lambda x: x.get("date_published") or "", reverse=True)

    archive["items"] = combined
    archive["item_count"] = len(combined)

    ARCHIVE_PATH.write_text(json.dumps(archive, indent=2, ensure_ascii=False))
    print(f"archive.json → {len(combined)} total items")


if __name__ == "__main__":
    main()
