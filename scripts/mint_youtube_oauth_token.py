#!/usr/bin/env python3
"""
scripts/mint_youtube_oauth_token.py — one-time helper to mint the OAuth
refresh token that scripts/fetch_youtube_api.py (and the daily
fetch-youtube-captions.yml workflow) need.

Run this YOURSELF, in your own terminal — not by asking an agent to run it —
since it opens a real browser for you to sign in as a manager of the
BKCHarvard channel and grant consent. It only prints the resulting
credentials to your own terminal for you to paste into GitHub's secret UI;
it never writes them to disk or anywhere in this repo.

Usage:
    pip install google-auth-oauthlib requests     # one-time
    python3 scripts/mint_youtube_oauth_token.py --client-secrets ~/Downloads/client_secret.json

A browser tab opens — sign in as a BKCHarvard channel manager and grant the
requested permission. Then copy the three printed values into:
    GitHub repo -> Settings -> Secrets and variables -> Actions
    -> New repository secret
        YT_OAUTH_CLIENT_ID
        YT_OAUTH_CLIENT_SECRET
        YT_OAUTH_REFRESH_TOKEN
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    sys.exit("Missing dependency. Run: pip install google-auth-oauthlib requests")

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--client-secrets",
        default=str(Path.home() / "Downloads" / "client_secret.json"),
        help="Path to the Desktop-app client_secret.json from Google Cloud Console",
    )
    args = ap.parse_args()

    path = Path(args.client_secrets)
    if not path.exists():
        sys.exit(f"Not found: {path}")

    client_config = json.loads(path.read_text())
    installed = client_config.get("installed")
    if not installed:
        sys.exit(
            "client_secret.json is not a Desktop-app credential (no 'installed' "
            "key). Create an OAuth Client ID of type 'Desktop app' in Google "
            "Cloud Console and download that instead."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(path), scopes=SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        sys.exit(
            "No refresh_token returned. This usually means you've already "
            "granted consent before and Google didn't re-issue one — revoke "
            "prior access at https://myaccount.google.com/permissions and "
            "re-run this script."
        )

    print("\nSuccess — set these as GitHub Actions repo secrets:")
    print("(repo -> Settings -> Secrets and variables -> Actions -> New repository secret)\n")
    print(f"  YT_OAUTH_CLIENT_ID      = {installed['client_id']}")
    print(f"  YT_OAUTH_CLIENT_SECRET  = {installed['client_secret']}")
    print(f"  YT_OAUTH_REFRESH_TOKEN  = {creds.refresh_token}")
    print("\nNothing above was written to disk or committed anywhere. Clear your")
    print("terminal scrollback after copying these in, if you'd like.")


if __name__ == "__main__":
    main()
