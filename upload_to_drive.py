#!/usr/bin/env python3
"""
Send video and caption directly to Make.com webhook
"""

import os
import json
import base64
import requests
from datetime import datetime

# Configuration
MAKE_WEBHOOK_URL = os.getenv('MAKE_WEBHOOK_URL')

def send_to_make_webhook(video_path, caption_data):
    """Send video and caption directly to Make.com webhook"""
    
    # Encode video as base64
    print(f"� Encoding video file...")
    with open(video_path, 'rb') as f:
        video_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    # Create payload
    payload = {
        'video': {
            'filename': os.path.basename(video_path),
            'data': video_base64,
            'mimeType': 'video/mp4'
        },
        'caption': {
            'title': caption_data.get('title', ''),
            'description': caption_data.get('description', ''),
            'hashtags': caption_data.get('hashtags', [])
        },
        'metadata': {
            'timestamp': datetime.utcnow().isoformat(),
            'runId': os.getenv('GITHUB_RUN_ID', 'manual'),
            'runNumber': os.getenv('GITHUB_RUN_NUMBER', 'manual')
        }
    }
    
    print(f"\n🔔 Triggering Make.com webhook...")
    print(f"   URL: {MAKE_WEBHOOK_URL}")
    
    try:
        response = requests.post(
            MAKE_WEBHOOK_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        
        print(f"✅ Make.com webhook triggered successfully!")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Warning: Could not trigger Make.com webhook")
        print(f"   Error: {e}")
        print(f"\n   This is OK if you're testing locally.")
        print(f"   Make sure to add MAKE_WEBHOOK_URL to GitHub secrets.")
        return False

def main():
    """Main function to send video to Make.com"""
    print("=" * 60)
    print("📤 SENDING VIDEO TO MAKE.COM")
    print("=" * 60)
    
    # Check if webhook URL is configured
    if not MAKE_WEBHOOK_URL:
        print("⚠️  MAKE_WEBHOOK_URL not set - cannot send to Make.com")
        print("   Add this to GitHub secrets after setting up Make.com")
        return
    
    # Check video exists
    video_path = 'generated/news_video.mp4'
    if not os.path.exists(video_path):
        print(f"❌ Error: Video file not found at {video_path}")
        return
    
    # Load caption
    caption_path = 'generated/caption.json'
    if not os.path.exists(caption_path):
        print(f"❌ Error: Caption file not found at {caption_path}")
        return
    
    with open(caption_path, 'r') as f:
        caption_data = json.load(f)
    
    print(f"\n📹 Video: {os.path.basename(video_path)}")
    print(f"📝 Title: {caption_data.get('title', 'N/A')}")
    print(f"📊 Size: {os.path.getsize(video_path) / 1024 / 1024:.2f} MB\n")
    
    # Send to Make.com
    success = send_to_make_webhook(video_path, caption_data)
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 SUCCESS! Video sent to Make.com")
        print("=" * 60)
        print("\nMake.com will now:")
        print("  1. Receive the video and caption")
        print("  2. Post to Facebook with caption")
        print("  3. Post to YouTube as Short")
        print("  4. Post to TikTok")
        print("\nCheck your Make.com dashboard for execution status!")
    else:
        print("\n" + "=" * 60)
        print("❌ Failed to send to Make.com")
        print("=" * 60)
        print("\nCheck:")
        print("  - MAKE_WEBHOOK_URL is correct")
        print("  - Make.com scenario is active (ON)")
        print("  - Internet connection is working")

if __name__ == '__main__':
    main()
