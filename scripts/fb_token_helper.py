#!/usr/bin/env python3
"""
Facebook Page Token Helper

Given:
  - Facebook App ID
  - Facebook App Secret
  - Short-lived USER access token (generated in Graph API Explorer with
    pages_show_list, pages_manage_posts, pages_read_engagement)
  - Optional Page ID

This script:
  1) Exchanges the short-lived user token for a long-lived user token
  2) Lists pages available to the user and selects your target Page
  3) Extracts the Page access token and verifies it's a PAGE token
  4) Prints ready-to-run gcloud commands to store FB_PAGE_ID and FB_PAGE_TOKEN

Usage (locally on your Mac):
  python scripts/fb_token_helper.py \
    --app-id 3015... \
    --app-secret 'YOUR_APP_SECRET' \
    --user-token 'SHORT_USER_TOKEN' \
    --page-id 61583593853793

Security: tokens are printed to your terminal so you can copy them into
Google Cloud Secret Manager. Treat them as sensitive and rotate if leaked.
"""

import argparse
import json
import os
import sys
from urllib.parse import urlencode

import requests


GRAPH = "https://graph.facebook.com/v19.0"


def die(msg: str, payload: dict | None = None):
    print(f"\n❌ {msg}")
    if payload is not None:
        try:
            print(json.dumps(payload, indent=2))
        except Exception:
            print(payload)
    sys.exit(1)


def get_long_lived_user_token(app_id: str, app_secret: str, short_user_token: str) -> str:
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_user_token,
    }
    r = requests.get(f"{GRAPH}/oauth/access_token", params=params, timeout=30)
    try:
        data = r.json()
    except Exception:
        die("Could not parse response from token exchange", {"status": r.status_code, "text": r.text})
    if "access_token" not in data:
        die("Token exchange failed (make sure the token was generated for THIS app in Graph API Explorer)", data)
    return data["access_token"]


def get_page_token(long_user_token: str, page_id: str | None) -> tuple[str, str]:
    """Return (page_id, page_token). If page_id is None, pick the first page."""
    r = requests.get(f"{GRAPH}/me/accounts", params={"access_token": long_user_token}, timeout=30)
    data = r.json()
    pages = data.get("data", [])
    if not pages:
        die("No pages found for this user. Ensure your user is an admin of the Page and permissions were granted.", data)
    chosen = None
    if page_id:
        for p in pages:
            if p.get("id") == str(page_id):
                chosen = p
                break
        if not chosen:
            die("Provided PAGE_ID not found in /me/accounts. Double-check the ID and permissions.", {"pages": pages})
    else:
        chosen = pages[0]
    pid = chosen.get("id")
    ptoken = chosen.get("access_token")
    if not ptoken:
        die("Selected page missing access_token in /me/accounts response.", chosen)
    return pid, ptoken


def debug_token(app_id: str, app_secret: str, token: str) -> dict:
    params = {"input_token": token, "access_token": f"{app_id}|{app_secret}"}
    r = requests.get(f"{GRAPH}/debug_token", params=params, timeout=30)
    return r.json()


def save_commands(project_id: str, page_id: str, page_token: str) -> str:
    os.makedirs("generated", exist_ok=True)
    path = os.path.join("generated", "fb_gcloud_commands.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env bash\nset -euo pipefail\n\n")
        f.write(f"PROJECT_ID={project_id}\n")
        f.write(f"FB_PAGE_ID={page_id}\n")
        f.write("FB_PAGE_TOKEN=\"" + page_token.replace("\"", "\\\"") + "\"\n\n")
        f.write("printf '%s' \"$FB_PAGE_ID\" | gcloud secrets create FB_PAGE_ID --data-file=- --project \"$PROJECT_ID\" || \\\n")
        f.write("printf '%s' \"$FB_PAGE_ID\" | gcloud secrets versions add FB_PAGE_ID --data-file=- --project \"$PROJECT_ID\"\n")
        f.write("printf '%s' \"$FB_PAGE_TOKEN\" | gcloud secrets create FB_PAGE_TOKEN --data-file=- --project \"$PROJECT_ID\" || \\\n")
        f.write("printf '%s' \"$FB_PAGE_TOKEN\" | gcloud secrets versions add FB_PAGE_TOKEN --data-file=- --project \"$PROJECT_ID\"\n")
    return path


def main():
    parser = argparse.ArgumentParser(description="Generate a Facebook Page token and print gcloud commands to store secrets.")
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--app-secret", required=True)
    parser.add_argument("--user-token", required=True, help="Short-lived USER token from Graph API Explorer")
    parser.add_argument("--page-id", help="Numeric Page ID (optional)")
    parser.add_argument("--project-id", default=os.environ.get("GCP_PROJECT_ID", "news-automation-477419"))
    args = parser.parse_args()

    print("\n🔐 Exchanging short-lived user token for a long-lived token...")
    long_user = get_long_lived_user_token(args.app_id, args.app_secret, args.user_token)
    print(f"✅ Long-lived user token acquired (prefix: {long_user[:12]}...)\n")

    print("🔎 Fetching pages and selecting target page...")
    pid, ptoken = get_page_token(long_user, args.page_id)
    print(f"✅ Page selected: {pid} (token prefix: {ptoken[:12]}...)\n")

    print("🧪 Verifying token type is PAGE...")
    info = debug_token(args.app_id, args.app_secret, ptoken)
    t = info.get("data", {}).get("type")
    if t != "PAGE":
        die("Token is not a PAGE token. Make sure you copied the page access_token from /me/accounts.", info)
    print("✅ Token verified as PAGE token.\n")

    script_path = save_commands(args.project_id, pid, ptoken)
    print("📄 Wrote gcloud secret commands to:", script_path)
    print("\nNext steps:")
    print("1) Open Cloud Shell and run the script contents to store FB_PAGE_ID and FB_PAGE_TOKEN:")
    print("   cat generated/fb_gcloud_commands.sh")
    print("   # Copy/paste into Cloud Shell (or upload the file)\n")
    print("2) (Re)deploy the Cloud Function (see scripts/deploy_cf.sh) and re-run your GitHub Action.")


if __name__ == "__main__":
    main()
