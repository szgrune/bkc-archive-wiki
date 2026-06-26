#!/usr/bin/env python3
"""
scripts/fetch_youtube.py — fetch all @BKCHarvard videos into the collection layer

Usage:
    python3 scripts/fetch_youtube.py             # fetch all new videos
    python3 scripts/fetch_youtube.py --dry-run   # list new videos, no writes
    python3 scripts/fetch_youtube.py --limit 50  # cap new videos processed

Requirements (one-time):
    pip install youtube-transcript-api requests

Avoiding YouTube IP blocks (bulk transcript fetching):
    YouTube rate-limits the transcript endpoint after ~50 requests from one IP.
    Route fetches through proxies and the script rotates across them on a block:
        export YT_PROXY_FILE=scripts/.proxies   # one proxy per line; Webshare's
                                                 # 'Proxy List' export works as-is
                                                 # (host:port:user:pass)
    See load_proxy_configs() for Webshare-residential and single-proxy options.
    When all configured proxies are blocked, the run aborts cleanly after
    BLOCK_ABORT_THRESHOLD; wait for a cooldown and re-run to resume.

How it works:
    1. Enumerates every video on the BKCHarvard YouTube channel via YouTube's
       internal Innertube browse API (no API key, no media download).
    2. Fetches each video's watch page to extract metadata (exact publish date,
       description, duration, channel id).
    3. Fetches captions via youtube-transcript-api — prefers human-authored
       ("manual"), falls back to YouTube ASR ("yt_auto"), records null if
       neither exists.
    4. Writes results into a self-contained, RAG-ready collection layer
       (it NEVER touches raw/archive.json — that integration is deferred):

           collection/
           ├── collection.json          manifest (id, defaults, sources)
           ├── json/youtube.json        metadata catalog — 1 entry per video,
           │                            with a pointer to its transcript file
           └── txt/youtube/yt_<id>.txt  one plain-text transcript per video
                                        ([HH:MM:SS] line prefixes preserved)

       Each catalog entry mirrors the archive.json item shape (so it can be
       merged into items[] later) plus `youtube` and `transcript` blocks.

Resumability:
    Each transcript .txt is written immediately and progress is staged to
    collection/json/.youtube-staging.json after every video. If interrupted,
    just re-run — videos already in the catalog (or with an existing .txt /
    staging entry) are detected and skipped automatically.
"""

import json
import os
import re
import time
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone


def atomic_write(path, text):
    """
    Write text to `path` atomically: write a temp file in the same directory,
    flush+fsync, then os.replace() over the target. A crash mid-write leaves
    either the previous complete file or the new one — never a truncated file,
    so resume state can't be corrupted by an interruption.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

# ── dependency check ──────────────────────────────────────────────────────────
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    import requests
except ImportError as e:
    print(f"Missing: {e}\nRun: pip install youtube-transcript-api requests",
          file=sys.stderr)
    sys.exit(1)

# Transient/rate-limit exceptions worth retrying with backoff. Names vary across
# youtube-transcript-api versions, so resolve them defensively (fall back to a
# generic Exception match if a given class isn't present in this install).
_RETRYABLE_CAPTION_ERRORS = []
for _name in ("RequestBlocked", "IpBlocked", "TooManyRequests",
              "YouTubeRequestFailed"):
    try:
        import youtube_transcript_api as _yta_mod
        _exc = getattr(_yta_mod, _name, None)
        if _exc is None:
            _exc = getattr(getattr(_yta_mod, "_errors", None), _name, None)
        if isinstance(_exc, type) and issubclass(_exc, Exception):
            _RETRYABLE_CAPTION_ERRORS.append(_exc)
    except Exception:
        pass
# Network-level failures (dead/slow/blocked proxies) are also retryable — they
# must rotate proxies, NOT be misclassified as "video has no captions".
_RETRYABLE_CAPTION_ERRORS.extend([
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.ProxyError,
])
_RETRYABLE_CAPTION_ERRORS = tuple(_RETRYABLE_CAPTION_ERRORS)

# ── paths & constants ─────────────────────────────────────────────────────────
CHANNEL_URL  = "https://www.youtube.com/@BKCHarvard"
CHANNEL_ID   = "UCuLGmD72gJDBwmLw06X58SA"   # confirmed from og:url
CHANNEL_NAME = "Berkman Klein Center"

WIKI_ROOT       = Path(__file__).parent.parent
COLLECTION_DIR  = WIKI_ROOT / "collection"
CATALOG_PATH    = COLLECTION_DIR / "json" / "youtube.json"
TRANSCRIPT_DIR  = COLLECTION_DIR / "txt" / "youtube"
MANIFEST_PATH   = COLLECTION_DIR / "collection.json"
STAGING_PATH    = COLLECTION_DIR / "json" / ".youtube-staging.json"

# Existing immutable TagTeam source — READ-ONLY here, used only to avoid
# re-adding videos that TagTeam already surfaced. Never written by this script.
ARCHIVE_PATH = WIKI_ROOT / "raw" / "archive.json"

PAGE_DELAY   = 0.3   # seconds between per-video watch-page GETs
INNERTUBE_DELAY = 0.5   # seconds between continuation calls
CAPTION_DELAY   = 1.0   # seconds after each caption fetch (pacing to avoid blocks)
CAPTION_TIMEOUT = 20    # per-request timeout (s) for transcript fetches — bounds
                        # hangs on dead/slow proxies so the run can rotate/fail fast
CAPTION_RETRIES = 2     # attempts per proxy before rotating / giving up
CAPTION_BACKOFF = 3.0   # base seconds for exponential backoff between retries
                        # (kept short: when fully blocked, rotating or aborting
                        #  recovers, not waiting — so we fail fast)
# Abort the run after this many CONSECUTIVE blocked videos: once YouTube
# IP-blocks the transcript endpoint, every further fetch fails, so continuing
# only wastes time and (worse) would mark caption-bearing videos as "none".
# Blocked videos are never cataloged, so they are retried on the next run.
BLOCK_ABORT_THRESHOLD = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

LANG_PREFS = ["en", "en-US", "en-GB", "en-CA"]

NAME_STOPWORDS = {
    "BKC", "Harvard", "Center", "Panel", "Discussion", "Event", "Berkman", "Klein",
    "Symposium", "Workshop", "Forum", "Conference", "Internet", "Digital", "AI",
    "Technology", "Policy", "Law", "Talk", "Lecture", "Seminar", "Keynote",
    "Fireside", "Chat", "Conversation", "The", "And", "With", "Of", "In", "On",
    "Virtual", "Online", "Live", "Session", "Series", "Season", "Episode",
    "New", "Your", "Our", "Their", "Join", "How", "Why", "What", "When", "An",
}

# ── helpers ───────────────────────────────────────────────────────────────────

def parse_iso_duration(s):
    """'PT1H23M45S' → int seconds, or None."""
    if not s:
        return None
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if not m:
        return None
    h, mi, sc = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + sc


def normalize_date(d):
    """Normalize YouTube upload dates to ISO 8601 with +00:00 offset."""
    if not d:
        return ""
    d = d.strip()
    # bare date: 2024-03-15
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d + "T00:00:00.000+00:00"
    # trailing Z
    if d.endswith("Z"):
        d = d[:-1] + "+00:00"
    # missing milliseconds before offset
    if re.search(r"T\d{2}:\d{2}:\d{2}[+-]", d) and "." not in d:
        d = re.sub(r"(T\d{2}:\d{2}:\d{2})([+-])", r"\1.000\2", d)
    return d


def fmt_captions(entries):
    """FetchedTranscriptSnippet iterable → '[HH:MM:SS] text\\n...' string."""
    lines = []
    for e in entries:
        start = e.start
        h  = int(start // 3600)
        mi = int((start % 3600) // 60)
        sc = int(start % 60)
        lines.append(f"[{h:02d}:{mi:02d}:{sc:02d}] {e.text.strip()}")
    return "\n".join(lines)


def _is_name_like(s):
    words = s.strip().split()
    if not 2 <= len(words) <= 4:
        return False
    if not all(w and w[0].isupper() for w in words):
        return False
    if any(w in NAME_STOPWORDS for w in words):
        return False
    # reject all-caps tokens (acronyms / org names)
    if any(w.isupper() and len(w) > 1 for w in words):
        return False
    # reject words containing digits
    if any(any(c.isdigit() for c in w) for w in words):
        return False
    return True


def extract_speakers(title, description=""):
    """Heuristic extraction of speaker names from a YouTube video title."""
    found = []

    # "Title | Name"  or  "Title | Name and Name"  or  "Title | Name, Name"
    pipe = re.search(r"\|\s*([^|]+)$", title)
    if pipe:
        for part in re.split(r"\s+and\s+|,\s*", pipe.group(1)):
            p = part.strip().rstrip(".")
            if _is_name_like(p):
                found.append(p)

    # "Title — Name"  or  "Title – Name"
    if not found:
        dash = re.search(r"[—–]\s*([^—–|]+)$", title)
        if dash:
            n = dash.group(1).strip()
            if _is_name_like(n):
                found.append(n)

    # "… with First Last"
    if not found:
        m = re.search(r"\bwith\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", title)
        if m and _is_name_like(m.group(1)):
            found.append(m.group(1))

    # "First Last on Topic" (at start of title)
    if not found:
        m = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+on\s+", title)
        if m and _is_name_like(m.group(1)):
            found.append(m.group(1))

    return found


# ── channel enumeration ───────────────────────────────────────────────────────

def _extract_lockup_videos(items):
    """Pull (videoId, title) from a list of richItemRenderer / lockupViewModel items."""
    results = []
    for item in items:
        lvm = (item.get("richItemRenderer", {})
                   .get("content", {})
                   .get("lockupViewModel", {}))
        if not lvm:
            continue
        video_id = lvm.get("contentId", "")
        if not video_id:
            continue
        title = (lvm.get("metadata", {})
                    .get("lockupMetadataViewModel", {})
                    .get("title", {})
                    .get("content", ""))
        results.append({"videoId": video_id, "title": title})
    return results


def iter_channel_videos(session):
    """
    Yield {videoId, title} for every video on the BKCHarvard channel.

    Uses YouTube's Innertube browse API directly — scrapetube 2.6 is broken
    because YouTube now returns lockupViewModel instead of videoRenderer.
    """
    url = CHANNEL_URL + "/videos?view=0&flow=grid"

    # ── initial page ──────────────────────────────────────────────────────────
    session.cookies.set("CONSENT", "YES+cb", domain=".youtube.com")
    r = session.get(url, params={"ucbcb": 1}, timeout=25)
    r.raise_for_status()
    html = r.text

    # client version (needed for continuation requests)
    cv_m = re.search(r'"clientVersion"\s*:\s*"([^"]+)"', html)
    client_version = cv_m.group(1) if cv_m else "2.20240101"

    # Innertube API key
    ak_m = re.search(r'"innertubeApiKey"\s*:\s*"([^"]+)"', html)
    api_key = ak_m.group(1) if ak_m else ""

    # parse ytInitialData using raw_decode for robustness
    d_start = html.find("var ytInitialData = ")
    if d_start == -1:
        raise RuntimeError("ytInitialData not found in channel page")
    d_start += len("var ytInitialData = ")
    data, _ = json.JSONDecoder().raw_decode(html, d_start)

    # find richGridRenderer.contents
    def _find(d, k):
        if isinstance(d, dict):
            for dk, dv in d.items():
                if dk == k:
                    yield dv
                else:
                    yield from _find(dv, k)
        elif isinstance(d, list):
            for i in d:
                yield from _find(i, k)

    rgr = next(_find(data, "richGridRenderer"), None)
    if not rgr:
        raise RuntimeError("richGridRenderer not found — channel page structure changed")

    contents = rgr.get("contents", [])

    for item in _extract_lockup_videos(contents):
        yield item

    # ── pagination ────────────────────────────────────────────────────────────
    session.headers["X-YouTube-Client-Name"] = "1"
    session.headers["X-YouTube-Client-Version"] = client_version

    page = 1
    while True:
        cont_item = next(
            (c for c in contents if "continuationItemRenderer" in c), None
        )
        if not cont_item:
            break

        token = (cont_item["continuationItemRenderer"]
                          .get("continuationEndpoint", {})
                          .get("continuationCommand", {})
                          .get("token", ""))
        if not token:
            break

        resp = session.post(
            "https://www.youtube.com/youtubei/v1/browse",
            params={"key": api_key},
            json={
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": client_version,
                    }
                },
                "continuation": token,
            },
            timeout=25,
        )
        resp.raise_for_status()
        rdata = resp.json()

        actions = rdata.get("onResponseReceivedActions", [])
        if not actions:
            break

        contents = (actions[0]
                        .get("appendContinuationItemsAction", {})
                        .get("continuationItems", []))
        if not contents:
            break

        page += 1
        videos = _extract_lockup_videos(contents)
        for item in videos:
            yield item

        time.sleep(INNERTUBE_DELAY)


# ── per-video metadata ────────────────────────────────────────────────────────

def fetch_page_meta(session, video_id):
    """
    GET /watch?v=VIDEO_ID and extract metadata.

    YouTube no longer serves JSON-LD on watch pages. We use:
      - <meta itemprop="uploadDate">  for exact publish date
      - <meta itemprop="duration">    for ISO duration
      - ytInitialPlayerResponse.videoDetails  for full description + channelId

    Returns dict with keys: date_published, description_html, description_full,
    duration_seconds, channel_id.
    """
    import html as htmllib

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r = session.get(url, timeout=25)
        r.raise_for_status()
        html_text = r.text

        def get_itemprop(prop):
            m = re.search(rf'<meta itemprop="{prop}" content="([^"]+)"', html_text)
            return htmllib.unescape(m.group(1)) if m else None

        # date + duration from itemprop meta tags
        date      = normalize_date(get_itemprop("uploadDate") or "")
        duration  = parse_iso_duration(get_itemprop("duration") or "")

        # full description + channelId from ytInitialPlayerResponse.videoDetails
        description = ""
        ch_id = CHANNEL_ID
        ipr_m = re.search(r"var ytInitialPlayerResponse\s*=\s*", html_text)
        if ipr_m:
            ipr, _ = json.JSONDecoder().raw_decode(html_text, ipr_m.end())
            vd = ipr.get("videoDetails", {})
            description = vd.get("shortDescription", "")
            ch_id = vd.get("channelId", CHANNEL_ID)

        # fallback: og:description if ytInitialPlayerResponse missed
        if not description:
            og_m = re.search(
                r'<meta property="og:description" content="([^"]+)"', html_text
            )
            if og_m:
                description = htmllib.unescape(og_m.group(1))

        # For display: first 2 paragraphs as HTML <p> tags
        paras = [p.strip() for p in description.split("\n\n") if p.strip()]
        desc_html = "\n".join(
            f"<p>{p.replace(chr(10), ' ')}</p>" for p in paras[:2]
        )

        return {
            "date_published":   date,
            "description_html": desc_html,
            "description_full": description,
            "duration_seconds": duration,
            "channel_id":       ch_id,
        }

    except Exception as e:
        print(f"  [warn] page meta {video_id}: {e}", file=sys.stderr)
        return {}


# ── captions ──────────────────────────────────────────────────────────────────

def _parse_proxy_line(line):
    """
    Parse one proxy spec into an http(s) URL. Accepts:
      http://user:pass@host:port  (full URL, used as-is)
      host:port:user:pass         (Webshare proxy-list format)
      host:port
    Returns a URL string, or None to skip the line.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "://" in line:
        return line
    parts = line.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    if len(parts) == 2:
        host, port = parts
        return f"http://{host}:{port}"
    print(f"  [warn] unrecognized proxy line skipped: {line}", file=sys.stderr)
    return None


def load_proxy_configs():
    """
    Build an ordered list of (label, ProxyConfig|None) the client can rotate
    through when YouTube blocks one. Configure via environment:

      YT_PROXY_FILE   path to a file with one proxy per line (Webshare 'Proxy
                      List' export works directly — host:port:user:pass). Best
                      for the free tier: all ~10 proxies are rotated on blocks.
      WEBSHARE_PROXY_USERNAME / WEBSHARE_PROXY_PASSWORD
                      Webshare *residential* rotating endpoint (paid tier).
      YT_PROXY_HTTP / YT_PROXY_HTTPS
                      a single generic proxy URL.

    With nothing set, returns a single direct (no-proxy) config — same as before.
    """
    try:
        from youtube_transcript_api.proxies import (
            WebshareProxyConfig, GenericProxyConfig,
        )
    except Exception as e:
        print(f"  [warn] proxy support unavailable: {e}", file=sys.stderr)
        return [("direct", None)]

    configs = []

    pfile = os.environ.get("YT_PROXY_FILE")
    if pfile and Path(pfile).exists():
        for raw in Path(pfile).read_text().splitlines():
            url = _parse_proxy_line(raw)
            if url:
                host = url.split("@")[-1]
                configs.append(
                    (f"file:{host}", GenericProxyConfig(http_url=url, https_url=url))
                )
        if configs:
            print(f"Loaded {len(configs)} proxies from {pfile} (rotating on blocks).")
            return configs
        print(f"  [warn] no usable proxies in {pfile}", file=sys.stderr)

    ws_user = os.environ.get("WEBSHARE_PROXY_USERNAME")
    ws_pass = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if ws_user and ws_pass:
        print("Using Webshare residential proxy for transcript fetches.")
        return [("webshare", WebshareProxyConfig(
            proxy_username=ws_user, proxy_password=ws_pass))]

    http = os.environ.get("YT_PROXY_HTTP")
    https = os.environ.get("YT_PROXY_HTTPS")
    if http or https:
        print("Using generic proxy for transcript fetches.")
        return [("generic", GenericProxyConfig(http_url=http, https_url=https))]

    return [("direct", None)]


PROXY_CONFIGS = load_proxy_configs()
_proxy_idx = 0


class _TimeoutSession(requests.Session):
    """requests.Session that injects a default timeout into every request, so a
    dead/slow proxy can't hang the transcript fetch forever."""
    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", CAPTION_TIMEOUT)
        return super().request(*args, **kwargs)


def _make_api(config):
    # Pass our own timeout-bounded session; YouTubeTranscriptApi still applies
    # proxy_config (sets session.proxies) on top of it.
    return YouTubeTranscriptApi(proxy_config=config, http_client=_TimeoutSession())


_yt_api = _make_api(PROXY_CONFIGS[_proxy_idx][1])


def _advance_proxy():
    """Rotate to the next configured proxy and rebuild the client."""
    global _proxy_idx, _yt_api
    _proxy_idx = (_proxy_idx + 1) % len(PROXY_CONFIGS)
    _yt_api = _make_api(PROXY_CONFIGS[_proxy_idx][1])
    return PROXY_CONFIGS[_proxy_idx][0]


def _safe_fetch(t):
    """Fetch a transcript track; re-raise retryable block errors, swallow the rest."""
    try:
        return list(t.fetch())
    except _RETRYABLE_CAPTION_ERRORS:
        raise
    except Exception:
        return None


def _find_track(tlist, finder):
    """Run a tlist.find_* method; re-raise retryable errors, return None otherwise."""
    try:
        return finder(LANG_PREFS)
    except _RETRYABLE_CAPTION_ERRORS:
        raise
    except Exception:
        return None


def _fetch_captions_once(video_id):
    """
    One attempt. Returns (status, caption_type, captions_str):
      ('ok',   'manual'|'yt_auto', text)  — captions retrieved
      ('none', None, None)                — genuinely no captions for this video
    Lets retryable block errors propagate to the retry loop in fetch_captions().
    """
    try:
        tlist = _yt_api.list(video_id)   # retryable errors propagate
    except _RETRYABLE_CAPTION_ERRORS:
        raise
    except Exception:
        # transcripts disabled / video unavailable / no transcript list → genuine none
        return "none", None, None

    # prefer manual
    t = _find_track(tlist, tlist.find_manually_created_transcript)
    if t is not None:
        entries = _safe_fetch(t)
        if entries is not None:
            return "ok", "manual", fmt_captions(entries)

    # fall back to auto-generated
    t = _find_track(tlist, tlist.find_generated_transcript)
    if t is not None:
        entries = _safe_fetch(t)
        if entries is not None:
            return "ok", "yt_auto", fmt_captions(entries)

    # any available language as last resort
    for t in tlist:
        entries = _safe_fetch(t)
        if entries is not None:
            cap_type = "yt_auto" if t.is_generated else "manual"
            return "ok", cap_type, fmt_captions(entries)

    return "none", None, None


def fetch_captions(video_id):
    """
    Returns (status, caption_type, captions_str), retrying transient YouTube
    rate-limit blocks with exponential backoff.

    status: 'ok'      — captions retrieved (caption_type is 'manual'|'yt_auto')
            'none'    — video genuinely has no captions (safe to record + skip later)
            'blocked' — YouTube IP-blocked us after retries (DO NOT catalog; retry next run)
    """
    for attempt in range(1, CAPTION_RETRIES + 1):
        try:
            return _fetch_captions_once(video_id)
        except _RETRYABLE_CAPTION_ERRORS as e:
            if attempt == CAPTION_RETRIES:
                print(f"  [warn] captions blocked {video_id} after {attempt} "
                      f"tries: {type(e).__name__}", file=sys.stderr)
                return "blocked", None, None
            wait = CAPTION_BACKOFF * (2 ** (attempt - 1))
            print(f"  [retry] captions {video_id}: {type(e).__name__}; "
                  f"waiting {wait:.0f}s ({attempt}/{CAPTION_RETRIES})",
                  file=sys.stderr)
            time.sleep(wait)
        except Exception:
            return "none", None, None
    return "blocked", None, None


def fetch_captions_rotating(video_id):
    """
    Wrap fetch_captions with proxy rotation: if the current proxy is blocked,
    rotate to the next configured proxy and retry the same video. Returns
    'blocked' only when EVERY configured proxy is blocked for this video
    (i.e. all are in cooldown) — that's what trips the run's abort threshold.
    """
    n = len(PROXY_CONFIGS)
    for _ in range(n):
        status, cap_type, caps = fetch_captions(video_id)
        if status != "blocked" or n == 1:
            return status, cap_type, caps
        label = _advance_proxy()
        print(f"  [proxy] blocked — rotating to proxy "
              f"{_proxy_idx + 1}/{n} ({label})", file=sys.stderr)
    return "blocked", None, None


# ── item builder ──────────────────────────────────────────────────────────────

def transcript_relpath(video_id):
    """Collection-relative path to a video's transcript .txt."""
    return f"txt/youtube/yt_{video_id}.txt"


def write_transcript(video_id, captions):
    """
    Write the transcript string to txt/youtube/yt_<id>.txt and return
    (word_count, char_count). Writing it first acts as the per-video checkpoint.
    """
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"yt_{video_id}.txt"
    atomic_write(path, captions)
    return len(captions.split()), len(captions)


def build_catalog_entry(video_stub, page_meta, cap_type, captions):
    """
    Build a metadata catalog entry (NO inline transcript text). Mirrors the
    archive.json item shape so entries can later be merged into items[], plus
    `youtube` and `transcript` blocks. The transcript text lives in its own
    .txt file, referenced by `transcript.path`.
    """
    video_id = video_stub["videoId"]
    title    = video_stub["title"]

    date  = page_meta.get("date_published", "")
    dur   = page_meta.get("duration_seconds")
    ch_id = page_meta.get("channel_id", CHANNEL_ID)

    speakers = extract_speakers(title, page_meta.get("description_full", ""))
    authors  = ", ".join(speakers) if speakers else CHANNEL_NAME

    thumb = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"

    has_caps = bool(cap_type and captions)
    if has_caps:
        words = len(captions.split())
        chars = len(captions)
        transcript = {
            "available":   True,
            "format":      "txt",
            "path":        transcript_relpath(video_id),
            "word_count":  words,
            "char_count":  chars,
        }
    else:
        transcript = {
            "available":   False,
            "format":      None,
            "path":        None,
            "word_count":  0,
            "char_count":  0,
        }

    return {
        "id":             f"yt_{video_id}",
        "title":          title,
        "url":            f"https://www.youtube.com/watch?v={video_id}",
        "guid":           video_id,
        "authors":        authors,
        "date_published": date,
        "last_updated":   date,
        "tags":           ["bkc-video"],
        "description":    page_meta.get("description_html", ""),
        "content":        page_meta.get("description_full", ""),
        "youtube": {
            "video_id":         video_id,
            "channel_id":       ch_id,
            "channel_name":     CHANNEL_NAME,
            "duration_seconds": dur,
            "thumbnail_url":    thumb,
            "speakers":         speakers,
            "caption_language": "en" if cap_type else None,
            "caption_type":     cap_type,
        },
        "transcript": transcript,
    }


# ── collection bootstrap ────────────────────────────────────────────────────

def ensure_collection():
    """Create the collection dirs and write collection.json if it doesn't exist."""
    (COLLECTION_DIR / "json").mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    if not MANIFEST_PATH.exists():
        manifest = {
            "id":          "bkc-archive",
            "title":       "BKC Archive Collection",
            "description": (
                "Berkman Klein Center archive collection — raw source layer "
                "for RAG ingestion. YouTube video metadata + transcripts; "
                "archive.json (TagTeam items) is added during a later "
                "canonicalization step."
            ),
            "defaults": {
                "embeddingsModel": None,
                "chunkSize":       1000,
                "chunkOverlap":    200,
            },
            "sources": [
                {
                    "format":      "json",
                    "path":        "json/youtube.json",
                    "archiveType": "item",
                },
                {
                    "format":       "txt",
                    "path":         "txt/youtube",
                    "archiveType":  "raw",
                    "metadataFrom": "json/youtube.json",
                },
            ],
        }
        atomic_write(
            MANIFEST_PATH, json.dumps(manifest, indent=2, ensure_ascii=False)
        )


# ── main ──────────────────────────────────────────────────────────────────────

def load_catalog():
    """Load the existing youtube.json catalog, or a fresh empty envelope."""
    if CATALOG_PATH.exists():
        return json.loads(CATALOG_PATH.read_text())
    return {
        "source":       CHANNEL_URL,
        "channel_id":   CHANNEL_ID,
        "channel_name": CHANNEL_NAME,
        "scraped_at":   None,
        "item_count":   0,
        "items":        [],
    }


def main():
    ap = argparse.ArgumentParser(
        description="Fetch @BKCHarvard YouTube videos → collection/ (json + txt)"
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Enumerate new videos and print them; no network fetches or writes"
    )
    ap.add_argument(
        "--limit", type=int, default=None,
        help="Stop after processing this many new videos (for testing)"
    )
    ap.add_argument(
        "--caption-delay", type=float, default=CAPTION_DELAY,
        help=(f"Seconds between caption fetches (default {CAPTION_DELAY}). For an "
              f"unattended 'slow-and-steady' run on one residential IP, use a large "
              f"value (e.g. 30-45) to stay under YouTube's rate limit.")
    )
    ap.add_argument(
        "--block-cooldown", type=float, default=0.0,
        help=("If > 0, RIDE OUT rate-limit blocks instead of aborting: on an "
              "all-proxy block, sleep this many seconds and retry the same video. "
              "Makes a slow run self-healing (and tolerant of a block already in "
              "effect at startup). Recommended ~300-600 for the slow-and-steady run.")
    )
    ap.add_argument(
        "--max-cooldowns", type=int, default=20,
        help=("Abort after this many CONSECUTIVE block-cooldowns with no progress "
              "(safety valve against an indefinite spin). Default 20.")
    )
    args = ap.parse_args()

    # ── load existing state ───────────────────────────────────────────────────
    # archive.json is READ-ONLY here — only to skip videos TagTeam already has.
    archive = json.loads(ARCHIVE_PATH.read_text()) if ARCHIVE_PATH.exists() else {"items": []}
    catalog = load_catalog()
    if STAGING_PATH.exists():
        try:
            staging = json.loads(STAGING_PATH.read_text())
        except json.JSONDecodeError:
            print(f"ERROR: staging file is unreadable: {STAGING_PATH}\n"
                  f"  Inspect or delete it, then re-run. Transcripts already on "
                  f"disk are preserved; affected videos will simply be re-fetched.",
                  file=sys.stderr)
            sys.exit(1)
    else:
        staging = []

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
    if staging:
        print(f"  (will resume — {len(staging)} already staged)")

    # ── enumerate channel ─────────────────────────────────────────────────────
    print(f"Enumerating {CHANNEL_URL} …")
    session = requests.Session()
    session.headers.update(HEADERS)

    all_videos = list(iter_channel_videos(session))
    print(f"Channel total: {len(all_videos)} videos")

    new_videos = [
        v for v in all_videos
        if f"yt_{v['videoId']}" not in seen_ids
        and f"https://www.youtube.com/watch?v={v['videoId']}" not in seen_yt_urls
    ]
    print(f"New (not yet in catalog): {len(new_videos)}")

    # ── dry-run ───────────────────────────────────────────────────────────────
    if args.dry_run:
        for v in new_videos[:30]:
            print(f"  {v['videoId']}  {v['title'][:65]}")
        if len(new_videos) > 30:
            print(f"  … and {len(new_videos) - 30} more")
        return

    if not new_videos:
        print("Nothing new to fetch.")
        return

    if args.limit:
        new_videos = new_videos[: args.limit]
        print(f"Capped at {len(new_videos)} videos (--limit)")

    # ── prepare collection ──────────────────────────────────────────────────────
    ensure_collection()

    # ── per-video fetch ───────────────────────────────────────────────────────
    no_captions = []
    blocked_ids = set()         # unique videos blocked at least once this run
    consecutive_blocks = 0      # used in abort mode (block-cooldown == 0)
    consecutive_cooldowns = 0   # used in ride-out mode (block-cooldown > 0)
    aborted = False
    total = len(new_videos)

    # index-based loop so a cooldown can retry the SAME video (i not advanced)
    i = 0
    while i < total:
        v = new_videos[i]
        vid = v["videoId"]
        title_preview = v["title"][:55]
        print(f"[{i + 1:>4}/{total}] {vid}  {title_preview}")

        meta = fetch_page_meta(session, vid)
        time.sleep(PAGE_DELAY)

        status, cap_type, captions = fetch_captions_rotating(vid)
        time.sleep(args.caption_delay)

        if status == "blocked":
            blocked_ids.add(vid)
            # ── ride-out mode: sleep through the block and retry the same video ──
            if args.block_cooldown > 0:
                consecutive_cooldowns += 1
                if consecutive_cooldowns > args.max_cooldowns:
                    print(
                        f"\n  ── ABORTING: {consecutive_cooldowns - 1} consecutive "
                        f"cooldowns with no progress — giving up for now.\n"
                        f"     Progress is saved; blocked videos are NOT cataloged, "
                        f"so they resume automatically. Re-run later.\n"
                    )
                    aborted = True
                    break
                print(f"              caps=BLOCKED — cooling down "
                      f"{args.block_cooldown:.0f}s then retrying "
                      f"(cooldown {consecutive_cooldowns}/{args.max_cooldowns})")
                time.sleep(args.block_cooldown)
                continue   # retry SAME i
            # ── abort mode: give up after a short streak (original behavior) ──
            consecutive_blocks += 1
            print("              caps=BLOCKED (not cataloged — will retry next run)")
            if consecutive_blocks >= BLOCK_ABORT_THRESHOLD:
                print(
                    f"\n  ── ABORTING: {consecutive_blocks} consecutive IP blocks. "
                    f"YouTube is rate-limiting this IP.\n"
                    f"     Wait for a cooldown and re-run, or use --block-cooldown "
                    f"to ride out blocks automatically, or configure proxies via "
                    f"YT_PROXY_FILE (see load_proxy_configs).\n"
                    f"     Progress is saved; blocked videos are NOT cataloged, "
                    f"so they resume automatically.\n"
                )
                aborted = True
                break
            i += 1
            continue

        # progress made → reset both streak counters
        consecutive_blocks = 0
        consecutive_cooldowns = 0

        if cap_type is None:          # genuine "no captions" — record so we don't re-fetch forever
            no_captions.append(vid)
            cap_label = "no captions"
        else:
            # write transcript first — this is the per-video checkpoint
            words, _ = write_transcript(vid, captions)
            cap_label = f"{cap_type} ({words:,}w)"

        date_str = (meta.get("date_published") or "")[:10] or "no-date"
        print(f"              date={date_str}  caps={cap_label}")

        entry = build_catalog_entry(v, meta, cap_type, captions)
        staging.append(entry)

        # save staging after every video so a crash loses at most one video
        atomic_write(
            STAGING_PATH, json.dumps(staging, indent=2, ensure_ascii=False)
        )

        if (i + 1) % 25 == 0:
            print(
                f"\n  ── checkpoint {i + 1}/{total}"
                f" | {len(no_captions)} no-caption, {len(blocked_ids)} blocked "
                f"so far ──\n"
            )
        i += 1

    # ── merge staging → catalog (youtube.json ONLY — never archive.json) ────────
    print(f"\nMerging {len(staging)} staged videos into youtube.json …")

    combined = staging + catalog["items"]
    combined.sort(key=lambda x: x.get("date_published") or "", reverse=True)

    catalog["items"]      = combined
    catalog["item_count"] = len(combined)
    catalog["scraped_at"] = datetime.now(timezone.utc).isoformat()

    atomic_write(CATALOG_PATH, json.dumps(catalog, indent=2, ensure_ascii=False))
    print(f"youtube.json → {len(combined)} total videos")

    STAGING_PATH.unlink(missing_ok=True)
    print("Staging file removed.")

    # ── summary ───────────────────────────────────────────────────────────────
    cap_counts = {}
    for item in staging:
        ct = item.get("youtube", {}).get("caption_type")
        cap_counts[ct] = cap_counts.get(ct, 0) + 1

    print("\nCaption breakdown for this run:")
    for ct, n in sorted(cap_counts.items(), key=lambda x: x[0] or ""):
        label = ct or "none"
        print(f"  {label:10s} {n}")

    if no_captions:
        print(f"\nVideos with no captions ({len(no_captions)}):")
        for vid in no_captions[:15]:
            print(f"  https://www.youtube.com/watch?v={vid}")
        if len(no_captions) > 15:
            print(f"  … and {len(no_captions) - 15} more")

    if blocked_ids:
        print(f"\nBlocked by YouTube this run ({len(blocked_ids)}) — NOT cataloged, "
              f"will retry automatically on the next run.")

    if aborted:
        print("\nRun aborted early due to sustained IP blocking. Re-run after a "
              "cooldown (or with a proxy configured) to continue where it left off.")
        sys.exit(2)


if __name__ == "__main__":
    main()
