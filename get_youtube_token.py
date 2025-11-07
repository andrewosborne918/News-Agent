#!/usr/bin/env python3
"""
One-time script to get a YouTube refresh token.
Run this locally on your computer (it opens your browser to authorize).

Usage options:
  - Interactive prompts (default)
  - Or pass flags/env vars:
      python get_youtube_token.py \
        --client-id "$YT_CLIENT_ID" \
        --client-secret "$YT_CLIENT_SECRET"

Environment variable fallbacks:
  YT_CLIENT_ID, YT_CLIENT_SECRET
"""

import os
import argparse
import google_auth_oauthlib.flow


def main():
    print("=" * 60)
    print("YouTube OAuth Token Generator")
    print("=" * 60)
    print("\nYou'll need:")
    print("1. Client ID from Google Cloud Console")
    print("2. Client Secret from Google Cloud Console")
    print("\nGet these from: https://console.cloud.google.com/apis/credentials")
    print("=" * 60)

    parser = argparse.ArgumentParser(description="Generate a YouTube refresh token")
    parser.add_argument("--client-id", dest="client_id", default=os.getenv("YT_CLIENT_ID"))
    parser.add_argument("--client-secret", dest="client_secret", default=os.getenv("YT_CLIENT_SECRET"))
    args = parser.parse_args()

    client_id = args.client_id
    client_secret = args.client_secret

    if not client_id:
        client_id = input("\nEnter Client ID: ").strip()
    if not client_secret:
        client_secret = input("Enter Client Secret: ").strip()

    if not client_id or not client_secret:
        print("\n❌ Error: Both Client ID and Secret are required!")
        raise SystemExit(1)

    print("\n🔐 Starting OAuth flow...")
    print("Your browser will open - sign in to the YouTube channel you want to post to\n")

    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )

    try:
        creds = flow.run_local_server(port=0)

        print("\n" + "=" * 60)
        print("✅ SUCCESS! Copy this refresh token:")
        print("=" * 60)
        print(creds.refresh_token)
        print("=" * 60)
        print("\nAdd this to Google Cloud Secret Manager:")
        print(
            f'  echo -n "{creds.refresh_token}" | gcloud secrets create YT_REFRESH_TOKEN --data-file=-'
        )
        print("(or add a new version if it already exists):")
        print(
            f'  echo -n "{creds.refresh_token}" | gcloud secrets versions add YT_REFRESH_TOKEN --data-file=-'
        )
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
