#!/usr/bin/env python3
"""
One-time script to get YouTube refresh token
Run this locally on your computer
"""

import google_auth_oauthlib.flow

print("="*60)
print("YouTube OAuth Token Generator")
print("="*60)
print("\nYou'll need:")
print("1. Client ID from Google Cloud Console")
print("2. Client Secret from Google Cloud Console")
print("\nGet these from: https://console.cloud.google.com/apis/credentials")
print("="*60)

CLIENT_ID = input("\nEnter Client ID: ").strip()
CLIENT_SECRET = input("Enter Client Secret: ").strip()

if not CLIENT_ID or not CLIENT_SECRET:
    print("\n❌ Error: Both Client ID and Secret are required!")
    exit(1)

print("\n🔐 Starting OAuth flow...")
print("Your browser will open - sign in to the YouTube channel you want to post to\n")

flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]
        }
    },
    scopes=["https://www.googleapis.com/auth/youtube.upload"]
)

try:
    creds = flow.run_local_server(port=0)
    
    print("\n" + "="*60)
    print("✅ SUCCESS! Copy this refresh token:")
    print("="*60)
    print(creds.refresh_token)
    print("="*60)
    print("\nAdd this to Google Cloud Secret Manager:")
    print(f'  echo -n "{creds.refresh_token}" | gcloud secrets create YT_REFRESH_TOKEN --data-file=-')
    print("="*60)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    exit(1)
