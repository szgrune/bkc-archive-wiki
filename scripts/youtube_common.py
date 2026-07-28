"""
scripts/youtube_common.py — shared constants and helpers for the YouTube
collection pipeline. Used by both fetch_youtube.py (scraped: Innertube +
youtube-transcript-api) and fetch_youtube_api.py (official Data API v3 +
OAuth). Kept here so the two fetch mechanisms write into the exact same
collection/ layout and can resume each other's progress.
"""

import json
import os
import re
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
WIKI_ROOT       = Path(__file__).parent.parent
COLLECTION_DIR  = WIKI_ROOT / "collection"
CATALOG_PATH    = COLLECTION_DIR / "json" / "youtube.json"
TRANSCRIPT_DIR  = COLLECTION_DIR / "txt" / "youtube"
MANIFEST_PATH   = COLLECTION_DIR / "collection.json"
STAGING_PATH    = COLLECTION_DIR / "json" / ".youtube-staging.json"

# Existing immutable TagTeam source — READ-ONLY here, used only to avoid
# re-adding videos that TagTeam already surfaced. Never written by these scripts.
ARCHIVE_PATH = WIKI_ROOT / "raw" / "archive.json"

# ── channel ───────────────────────────────────────────────────────────────────
CHANNEL_URL  = "https://www.youtube.com/@BKCHarvard"
CHANNEL_ID   = "UCuLGmD72gJDBwmLw06X58SA"   # confirmed from og:url
CHANNEL_NAME = "Berkman Klein Center"

LANG_PREFS = ["en", "en-US", "en-GB", "en-CA"]

NAME_STOPWORDS = {
    "BKC", "Harvard", "Center", "Panel", "Discussion", "Event", "Berkman", "Klein",
    "Symposium", "Workshop", "Forum", "Conference", "Internet", "Digital", "AI",
    "Technology", "Policy", "Law", "Talk", "Lecture", "Seminar", "Keynote",
    "Fireside", "Chat", "Conversation", "The", "And", "With", "Of", "In", "On",
    "Virtual", "Online", "Live", "Session", "Series", "Season", "Episode",
    "New", "Your", "Our", "Their", "Join", "How", "Why", "What", "When", "An",
}


# ── atomic writes ─────────────────────────────────────────────────────────────

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


# ── date/duration parsing ─────────────────────────────────────────────────────

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
    """Normalize a YouTube upload date to ISO 8601 with +00:00 offset."""
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


# ── speaker-name heuristics ───────────────────────────────────────────────────

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


# ── collection bootstrap / catalog ────────────────────────────────────────────

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
