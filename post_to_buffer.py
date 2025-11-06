#!/usr/bin/env python3
"""
Post video to Buffer for scheduled social media posting.
"""

import os
import sys
import requests
import json
from pathlib import Path

BUFFER_API_URL = "https://api.bufferapp.com/1"


def get_buffer_profile_ids(access_token):
    """Get all Buffer profile IDs for the authenticated user."""
    url = f"{BUFFER_API_URL}/profiles.json"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    profiles = response.json()
    print(f"📱 Found {len(profiles)} Buffer profiles:")
    for profile in profiles:
        service = profile.get('service', 'unknown')
        username = profile.get('formatted_username', 'N/A')
        profile_id = profile['_id']
        print(f"   • {service}: @{username} (ID: {profile_id})")
    
    return [p['_id'] for p in profiles]


def upload_media_to_buffer(access_token, video_path):
    """Upload video to Buffer's media endpoint."""
    url = f"{BUFFER_API_URL}/uploads.json"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    with open(video_path, 'rb') as video_file:
        files = {'media': video_file}
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()
    
    media_data = response.json()
    return media_data


def create_buffer_post(access_token, profile_ids, text, media_id=None, video_thumbnail=None):
    """Create a post in Buffer with optional media."""
    url = f"{BUFFER_API_URL}/updates/create.json"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Buffer expects profile_ids as an array
    data = {
        "profile_ids[]": profile_ids,
        "text": text,
        "shorten": False,  # Don't shorten links
    }
    
    # Add media if provided
    if media_id:
        data["media[video]"] = media_id
        if video_thumbnail:
            data["media[thumbnail]"] = video_thumbnail
    
    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    
    return response.json()


def load_caption_data(caption_file="generated/caption.json"):
    """Load the AI-generated caption from file."""
    caption_path = Path(caption_file)
    
    if not caption_path.exists():
        print(f"⚠️  Caption file not found: {caption_file}")
        return None
    
    with open(caption_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_caption_for_buffer(caption_data):
    """Format caption data for Buffer post."""
    if not caption_data:
        # Fallback caption
        return "� Today's political news analysis\n\n#News #Politics #Breaking"
    
    title = caption_data.get("title", "Political News Update")
    description = caption_data.get("description", "Watch for analysis")
    hashtags = caption_data.get("hashtags", ["News", "Politics"])
    
    # Format hashtags
    hashtag_string = " ".join([f"#{tag}" for tag in hashtags])
    
    # Create full caption
    caption = f"{title}\n\n{description}\n\n{hashtag_string}"
    
    return caption


def main():
    # Get Buffer access token from environment
    access_token = os.getenv("BUFFER_ACCESS_TOKEN")
    if not access_token:
        print("❌ Error: BUFFER_ACCESS_TOKEN environment variable not set")
        sys.exit(1)
    
    # Get video path (default to output/final.mp4)
    video_path = sys.argv[1] if len(sys.argv) > 1 else "output/final.mp4"
    video_file = Path(video_path)
    
    if not video_file.exists():
        print(f"❌ Error: Video file not found: {video_path}")
        sys.exit(1)
    
    # Get run_id for caption generation (optional)
    run_id = os.getenv("RUN_ID", "default")
    
    print("🚀 Posting video to Buffer...")
    print(f"📹 Video: {video_path} ({video_file.stat().st_size / 1024 / 1024:.2f} MB)")
    
    try:
        # Step 1: Get Buffer profile IDs
        profile_ids = get_buffer_profile_ids(access_token)
        
        if not profile_ids:
            print("❌ No Buffer profiles found. Please connect social accounts in Buffer.")
            sys.exit(1)
        
        # Step 2: Upload video
        print("📤 Uploading video to Buffer...")
        media_response = upload_media_to_buffer(access_token, video_path)
        media_id = media_response.get('media_id')
        
        if not media_id:
            print("❌ Failed to get media_id from upload response")
            print(f"Response: {json.dumps(media_response, indent=2)}")
            sys.exit(1)
        
        print(f"✅ Video uploaded successfully (media_id: {media_id})")
        
        # Step 3: Load AI-generated caption
        print("📝 Loading caption data...")
        caption_data = load_caption_data()
        caption = format_caption_for_buffer(caption_data)
        
        print(f"📝 Caption ({len(caption)} chars):")
        print("-" * 60)
        print(caption)
        print("-" * 60)
        print("📮 Creating Buffer post...")
        
        post_response = create_buffer_post(
            access_token=access_token,
            profile_ids=profile_ids,
            text=caption,
            media_id=media_id
        )
        
        print("✅ Post created successfully!")
        print(f"📊 Post details:")
        print(json.dumps(post_response, indent=2))
        
        # Check if post is scheduled or immediate
        if post_response.get('scheduled_at'):
            print(f"⏰ Post scheduled for: {post_response['scheduled_at']}")
        else:
            print("🚀 Post published immediately!")
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        if e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
