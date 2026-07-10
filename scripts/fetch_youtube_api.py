#!/usr/bin/env python3
"""
scripts/fetch_youtube_api.py — fetch @BKCHarvard captions via the official
YouTube Data API v3 (OAuth), instead of scraping (fetch_youtube.py).

Why this exists: fetch_youtube.py uses YouTube's internal Innertube API and
the youtube-transcript-api library, neither of which is officially sanctioned
access — see the ToS discussion this script grew out of. captions.download
only returns caption content when the caller is OAuth-authenticated as a
manager of the video's channel, which makes it the fully-authorized path for
BKC's own channel. The tradeoff is quota: the free tier is 10,000 units/day,
and a list+download pair costs 250 units, so ~40 videos/day (~1 month for the
~1,100-video backlog) unless a quota increase is granted (see
https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits —
that's a multi-week manual audit, not a self-service bump).

Writes into the SAME collection/ layout as fetch_youtube.py (shared dedup
state via youtube_common), so this can pick up wherever either script left
off, and vice versa.

Setup (one-time, by whoever administers the BKC channel's Google account):
    1. Create a Google Cloud project, enable "YouTube Data API v3".
    2. Create an OAuth 2.0 Client ID (type: Desktop app or Web app).
    3. Run the OAuth consent flow once, signed in as a manager of the
       BKCHarvard channel, requesting scope
       https://www.googleapis.com/auth/youtube.force-ssl — this mints a
       refresh token.
    4. Set as secrets/env vars: YT_OAUTH_CLIENT_ID, YT_OAUTH_CLIENT_SECRET,
       YT_OAUTH_REFRESH_TOKEN.

Usage:
    python3 scripts/fetch_youtube_api.py                    # fetch, budget 9000 units/day
    python3 scripts/fetch_youtube_api.py --quota-budget 5000
    python3 scripts/fetch_youtube_api.py --limit 5          # trial run
    python3 scripts/fetch_youtube_api.py --dry-run          # enumerate only;
                                                             # works with just
                                                             # YT_API_KEY, no OAuth

Env vars:
    YT_OAUTH_CLIENT_ID, YT_OAUTH_CLIENT_SECRET, YT_OAUTH_REFRESH_TOKEN
        required for any caption fetching (captions.list/download need
        channel-owner OAuth).
    YT_API_KEY
        optional; if OAuth isn't configured yet, --dry-run can enumerate the
        channel with just an API key (channels/playlistItems/videos are
        public read endpoints).

Credentials, where they live:
    Production (daily GitHub Actions run): repo Settings -> Secrets and
    variables -> Actions -> New repository secret, using the three env var
    names above verbatim — see .github/workflows/fetch-youtube-captions.yml.

    Local testing: this script does NOT auto-load a .env file (no dotenv
    dependency), so either export the three vars in your shell, or put them
    in a local .env (already in .gitignore — never commit real values) and
    load it manually before running:
        set -a; source .env; set +a
        python3 scripts/fetch_youtube_api.py --limit 1
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

from youtube_common import (
    CATALOG_PATH, STAGING_PATH, ARCHIVE_PATH, CHANNEL_ID, CHANNEL_NAME,
    LANG_PREFS, atomic_write, parse_iso_duration, normalize_date,
    extract_speakers, ensure_collection, load_catalog, transcript_relpath,
    write_transcript,
)

API_BASE = "https://www.googleapis.com/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

RESIDUE_PATH = CATALOG_PATH.parent.parent / "residue.txt"  # collection/residue.txt

# Quota costs (units) per the Data API v3 pricing table.
COST_CHANNELS_LIST     = 1
COST_PLAYLIST_ITEMS    = 1
COST_VIDEOS_LIST       = 1
COST_CAPTIONS_LIST     = 50
COST_CAPTIONS_DOWNLOAD = 200

DEFAULT_QUOTA_BUDGET = 9000  # leave headroom under the 10,000/day free quota


# ── auth / low-level client ───────────────────────────────────────────────────

class Quota:
    def __init__(self, budget):
        self.budget = budget
        self.used = 0

    def can_afford(self, cost):
        return self.used + cost <= self.budget

    def charge(self, cost):
        self.used += cost


def get_access_token():
    client_id = os.environ.get("YT_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("YT_OAUTH_CLIENT_SECRET")
    refresh_token = os.environ.get("YT_OAUTH_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=25)
    resp.raise_for_status()
    return resp.json()["access_token"]


class YTClient:
    """Thin wrapper: OAuth bearer token if available, else API-key query param
    (API key only works for public read endpoints — not captions.list/download)."""

    def __init__(self, access_token=None, api_key=None):
        self.session = requests.Session()
        self.api_key = None
        if access_token:
            self.session.headers["Authorization"] = f"Bearer {access_token}"
        elif api_key:
            self.api_key = api_key

    @property
    def authorized(self):
        return "Authorization" in self.session.headers

    def get(self, path, params, timeout=25):
        p = dict(params)
        if self.api_key:
            p["key"] = self.api_key
        return self.session.get(f"{API_BASE}/{path}", params=p, timeout=timeout)


# ── channel enumeration ───────────────────────────────────────────────────────

def get_uploads_playlist_id(client, quota):
    resp = client.get("channels", {"part": "contentDetails", "id": CHANNEL_ID})
    resp.raise_for_status()
    quota.charge(COST_CHANNELS_LIST)
    items = resp.json().get("items", [])
    if not items:
        raise RuntimeError(f"Channel {CHANNEL_ID} not found")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def iter_uploaded_video_ids(client, uploads_playlist_id, quota):
    page_token = None
    while True:
        params = {"part": "contentDetails", "playlistId": uploads_playlist_id,
                   "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        resp = client.get("playlistItems", params)
        resp.raise_for_status()
        quota.charge(COST_PLAYLIST_ITEMS)
        data = resp.json()
        for item in data.get("items", []):
            yield item["contentDetails"]["videoId"]
        page_token = data.get("nextPageToken")
        if not page_token:
            break


# ── per-video metadata ────────────────────────────────────────────────────────

def description_to_html(description):
    paras = [p.strip() for p in description.split("\n\n") if p.strip()]
    return "\n".join(f"<p>{p.replace(chr(10), ' ')}</p>" for p in paras[:2])


def fetch_videos_meta(client, video_ids, quota):
    """Batch metadata fetch (up to 50 ids costs 1 unit total)."""
    resp = client.get("videos", {"part": "snippet,contentDetails",
                                  "id": ",".join(video_ids), "maxResults": 50})
    resp.raise_for_status()
    quota.charge(COST_VIDEOS_LIST)
    out = {}
    for item in resp.json().get("items", []):
        sn = item.get("snippet", {})
        cd = item.get("contentDetails", {})
        out[item["id"]] = {
            "title":             sn.get("title", ""),
            "description_full":  sn.get("description", ""),
            "date_published":    normalize_date(sn.get("publishedAt", "")),
            "duration_seconds":  parse_iso_duration(cd.get("duration")),
            "channel_id":        sn.get("channelId", CHANNEL_ID),
        }
    return out


# ── captions ──────────────────────────────────────────────────────────────────

def list_caption_tracks(client, video_id, quota):
    resp = client.get("captions", {"part": "snippet", "videoId": video_id})
    quota.charge(COST_CAPTIONS_LIST)
    if resp.status_code != 200:
        return []
    return resp.json().get("items", [])


def select_caption_tracks(tracks):
    """Priority order to try downloading: manual+preferred-lang, ASR+preferred
    lang, any manual, any ASR."""
    def lang_rank(lang):
        try:
            return LANG_PREFS.index(lang)
        except ValueError:
            return len(LANG_PREFS)

    standard = [t for t in tracks
                if t["snippet"].get("trackKind", "").lower() == "standard"]
    asr = [t for t in tracks
           if t["snippet"].get("trackKind", "").lower() == "asr"]
    standard.sort(key=lambda t: lang_rank(t["snippet"].get("language", "")))
    asr.sort(key=lambda t: lang_rank(t["snippet"].get("language", "")))
    return standard + asr


def download_caption_track(client, track_id, quota):
    """Returns raw SRT text, or None if this track isn't downloadable (e.g.
    YouTube blocks ASR-track downloads even for the channel owner)."""
    resp = client.get(f"captions/{track_id}", {"tfmt": "srt"})
    quota.charge(COST_CAPTIONS_DOWNLOAD)
    if resp.status_code == 200:
        return resp.text
    if resp.status_code in (400, 403, 404):
        return None
    resp.raise_for_status()
    return None


_SRT_TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.]\d{3}\s*-->")
_TAG_RE = re.compile(r"<[^>]+>")


def parse_srt(text):
    """SRT text → '[HH:MM:SS] text\\n...' string, matching fetch_youtube.py's
    transcript format so both scripts produce interchangeable .txt files."""
    lines = []
    for block in re.split(r"\r?\n\r?\n+", text.strip()):
        block_lines = block.splitlines()
        time_idx = next((i for i, l in enumerate(block_lines) if "-->" in l), None)
        if time_idx is None:
            continue
        m = _SRT_TIME_RE.search(block_lines[time_idx])
        if not m:
            continue
        h, mi, sc = (int(x) for x in m.groups())
        txt = " ".join(_TAG_RE.sub("", l).strip()
                       for l in block_lines[time_idx + 1:] if l.strip())
        if txt:
            lines.append(f"[{h:02d}:{mi:02d}:{sc:02d}] {txt}")
    return "\n".join(lines)


# ── item builder ──────────────────────────────────────────────────────────────

def build_catalog_entry(video_id, meta, cap_type, captions):
    title = meta["title"]
    speakers = extract_speakers(title, meta.get("description_full", ""))
    authors = ", ".join(speakers) if speakers else CHANNEL_NAME
    thumb = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    date = meta.get("date_published", "")

    has_caps = bool(cap_type and captions)
    if has_caps:
        transcript = {
            "available":  True,
            "format":     "txt",
            "path":       transcript_relpath(video_id),
            "word_count": len(captions.split()),
            "char_count": len(captions),
        }
    else:
        transcript = {"available": False, "format": None, "path": None,
                       "word_count": 0, "char_count": 0}

    return {
        "id":             f"yt_{video_id}",
        "title":          title,
        "url":            f"https://www.youtube.com/watch?v={video_id}",
        "guid":           video_id,
        "authors":        authors,
        "date_published": date,
        "last_updated":   date,
        "tags":           ["bkc-video"],
        "description":    description_to_html(meta.get("description_full", "")),
        "content":        meta.get("description_full", ""),
        "youtube": {
            "video_id":         video_id,
            "channel_id":       meta.get("channel_id", CHANNEL_ID),
            "channel_name":     CHANNEL_NAME,
            "duration_seconds": meta.get("duration_seconds"),
            "thumbnail_url":    thumb,
            "speakers":         speakers,
            "caption_language": "en" if cap_type else None,
            "caption_type":     cap_type,
        },
        "transcript": transcript,
    }


def append_residue(video_ids):
    if not video_ids:
        return
    existing = set()
    if RESIDUE_PATH.exists():
        existing = {l.strip() for l in RESIDUE_PATH.read_text().splitlines() if l.strip()}
    existing |= set(video_ids)
    atomic_write(RESIDUE_PATH, "\n".join(sorted(existing)) + "\n")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Fetch @BKCHarvard captions via YouTube Data API v3 (OAuth)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--quota-budget", type=int, default=DEFAULT_QUOTA_BUDGET,
                     help=f"Max Data API units to spend this run (default {DEFAULT_QUOTA_BUDGET})")
    ap.add_argument("--limit", type=int, default=None,
                     help="Stop after processing this many new videos (for testing)")
    ap.add_argument("--dry-run", action="store_true",
                     help="Enumerate new videos and print them; no caption fetches")
    args = ap.parse_args()

    access_token = get_access_token()
    api_key = os.environ.get("YT_API_KEY")
    if not access_token and not api_key:
        sys.exit(
            "No credentials configured. Set YT_OAUTH_CLIENT_ID / "
            "YT_OAUTH_CLIENT_SECRET / YT_OAUTH_REFRESH_TOKEN for real fetches, "
            "or YT_API_KEY for a --dry-run enumeration only."
        )
    client = YTClient(access_token=access_token, api_key=api_key)

    quota = Quota(args.quota_budget)

    archive = json.loads(ARCHIVE_PATH.read_text()) if ARCHIVE_PATH.exists() else {"items": []}
    catalog = load_catalog()
    staging = json.loads(STAGING_PATH.read_text()) if STAGING_PATH.exists() else []

    seen_ids = {str(i["id"]) for i in archive["items"]}
    seen_ids |= {str(i["id"]) for i in catalog["items"]}
    seen_ids |= {str(i["id"]) for i in staging}
    seen_yt_urls = {
        i["url"] for i in archive["items"]
        if "youtube.com/watch" in i.get("url", "") or "youtu.be/" in i.get("url", "")
    }

    print(f"Catalog: {len(catalog['items'])} videos  |  "
          f"Archive (dedup): {len(archive['items'])} items  |  "
          f"Staging: {len(staging)} items")

    uploads_playlist_id = get_uploads_playlist_id(client, quota)
    all_video_ids = list(iter_uploaded_video_ids(client, uploads_playlist_id, quota))
    print(f"Channel total: {len(all_video_ids)} videos  (enumeration cost: {quota.used} units)")

    new_video_ids = [
        v for v in all_video_ids
        if f"yt_{v}" not in seen_ids
        and f"https://www.youtube.com/watch?v={v}" not in seen_yt_urls
    ]
    total_new = len(new_video_ids)
    print(f"New (not yet in catalog): {total_new}")

    if args.dry_run:
        for v in new_video_ids[:30]:
            print(f"  {v}")
        if len(new_video_ids) > 30:
            print(f"  … and {len(new_video_ids) - 30} more")
        return

    if not new_video_ids:
        print("Nothing new to fetch.")
        return

    if not client.authorized:
        sys.exit("OAuth credentials required for caption fetching (API key alone "
                  "can't call captions.list/download). See script docstring.")

    if args.limit:
        new_video_ids = new_video_ids[:args.limit]

    ensure_collection()

    no_captions = []       # video has zero caption tracks
    undownloadable = []    # tracks exist but every download attempt was refused
    cap_counts = {}
    processed = 0
    budget_exhausted = False

    CHUNK = 50
    for i in range(0, len(new_video_ids), CHUNK):
        if budget_exhausted:
            break
        chunk = new_video_ids[i:i + CHUNK]
        if not quota.can_afford(COST_VIDEOS_LIST):
            print("\nQuota budget reached — stopping before fetching more metadata.")
            break
        metas = fetch_videos_meta(client, chunk, quota)

        for vid in chunk:
            if args.limit and processed >= args.limit:
                budget_exhausted = True
                break
            if not quota.can_afford(COST_CAPTIONS_LIST):
                print(f"\nQuota budget reached after {processed}/{len(new_video_ids)} "
                      f"videos ({quota.used}/{quota.budget} units) — stopping. "
                      f"Remaining videos resume automatically on the next run.")
                budget_exhausted = True
                break

            meta = metas.get(vid)
            if meta is None:
                print(f"  [warn] {vid}: no metadata (deleted/private?) — skipping")
                continue

            print(f"[{processed + 1}/{len(new_video_ids)}] {vid}  {meta['title'][:55]}")

            tracks = list_caption_tracks(client, vid, quota)
            candidates = select_caption_tracks(tracks)

            cap_type, captions_text = None, None
            for track in candidates:
                if not quota.can_afford(COST_CAPTIONS_DOWNLOAD):
                    break
                body = download_caption_track(client, track["id"], quota)
                if body:
                    captions_text = parse_srt(body)
                    kind = track["snippet"].get("trackKind", "").lower()
                    cap_type = "yt_auto" if kind == "asr" else "manual"
                    break

            if cap_type is None:
                if not tracks:
                    no_captions.append(vid)
                    print("              no caption tracks")
                else:
                    undownloadable.append(vid)
                    print("              tracks exist but none downloadable (residue)")
            else:
                words, _ = write_transcript(vid, captions_text)
                print(f"              caps={cap_type} ({words:,}w)")

            entry = build_catalog_entry(vid, meta, cap_type, captions_text)
            staging.append(entry)
            atomic_write(STAGING_PATH, json.dumps(staging, indent=2, ensure_ascii=False))
            cap_counts[cap_type] = cap_counts.get(cap_type, 0) + 1
            processed += 1

    # ── merge staging → catalog ───────────────────────────────────────────────
    print(f"\nMerging {len(staging)} staged videos into youtube.json …")
    combined = staging + catalog["items"]
    combined.sort(key=lambda x: x.get("date_published") or "", reverse=True)
    catalog["items"] = combined
    catalog["item_count"] = len(combined)
    catalog["scraped_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write(CATALOG_PATH, json.dumps(catalog, indent=2, ensure_ascii=False))
    STAGING_PATH.unlink(missing_ok=True)
    print(f"youtube.json → {len(combined)} total videos")

    append_residue(no_captions + undownloadable)

    print(f"\nQuota used: {quota.used}/{quota.budget} units  |  "
          f"videos processed this run: {processed}")
    print("Caption breakdown for this run:")
    for ct, n in sorted(cap_counts.items(), key=lambda x: x[0] or ""):
        print(f"  {ct or 'none':10s} {n}")
    if no_captions or undownloadable:
        print(f"\n{len(no_captions)} with no caption tracks, "
              f"{len(undownloadable)} with tracks but refused on download — "
              f"appended to {RESIDUE_PATH.relative_to(RESIDUE_PATH.parent.parent)}")

    remaining = total_new - processed
    print(f"\n{max(remaining, 0)} new videos left for future runs.")


if __name__ == "__main__":
    main()
