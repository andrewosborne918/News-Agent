"""
Google Cloud Function: Automatically post videos to YouTube Shorts + Facebook
Triggers when a new video is uploaded to Google Cloud Storage
"""

import os
import tempfile
import time
import random
import json
from google.cloud import storage, secretmanager
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import requests

# Get project ID from environment (auto-injected by Cloud Functions)
PROJECT_ID = os.environ.get("GCP_PROJECT")

def _get_secret(name: str) -> str:
    """Retrieve secret from Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()
    path = client.secret_version_path(PROJECT_ID, name, "latest")
    response = client.access_secret_version(request={"name": path})
    return response.payload.data.decode()

def _download_from_gcs(bucket_name: str, blob_name: str) -> str:
    """Download file from Google Cloud Storage to temp file"""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    # Create temp file with proper extension
    _, ext = os.path.splitext(blob_name)
    fd, tmp = tempfile.mkstemp(suffix=ext or ".mp4")
    os.close(fd)
    
    print(f"Downloading gs://{bucket_name}/{blob_name} to {tmp}")
    blob.download_to_filename(tmp)
    
    # Get file size
    size_mb = os.path.getsize(tmp) / 1024 / 1024
    print(f"Downloaded {size_mb:.2f} MB")
    
    return tmp

def _upload_youtube(filepath: str, title: str, description: str, tags: list) -> str:
    """Upload video to YouTube as a Short"""
    print(f"Uploading to YouTube: {title}")
    
    # Create credentials from refresh token
    creds = Credentials(
        token=None,
        refresh_token=_get_secret("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=_get_secret("YT_CLIENT_ID"),
        client_secret=_get_secret("YT_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    
    # Build YouTube client
    youtube = build("youtube", "v3", credentials=creds)
    
    # Prepare video metadata
    body = {
        "snippet": {
            "title": title[:100],  # YouTube limit
            "description": description[:4900],  # YouTube limit
            "tags": tags[:20],  # Max 20 tags
            "categoryId": "25"  # News & Politics
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }
    
    # Upload video (resumable for large files)
    media = MediaFileUpload(
        filepath,
        chunksize=1024*1024,  # 1MB chunks
        resumable=True,
        mimetype="video/*"
    )
    
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )
    
    # Execute resumable upload
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload {int(status.progress() * 100)}% complete")
    
    video_id = response.get("id")
    print(f"✅ YouTube upload complete: https://youtube.com/shorts/{video_id}")
    
    return video_id

def _upload_facebook(filepath: str, description: str) -> str:
    """Upload video to Facebook Page"""
    print(f"Uploading to Facebook")
    
    page_id = _get_secret("FB_PAGE_ID")
    token = _get_secret("FB_PAGE_TOKEN")
    
    # Facebook Graph API endpoint for video upload
    url = f"https://graph-video.facebook.com/v19.0/{page_id}/videos"
    
    # Upload video file
    with open(filepath, "rb") as video_file:
        response = requests.post(
            url,
            data={
                "access_token": token,
                "description": description
            },
            files={"source": video_file},
            timeout=300  # 5 minute timeout for large files
        )
    
    response.raise_for_status()
    video_id = response.json().get("id")
    
    print(f"✅ Facebook upload complete: Video ID {video_id}")
    
    return video_id

def _derive_metadata(bucket: str, blob_name: str) -> tuple:
    """
    Extract metadata from filename and generate title/description/tags
    You can enhance this to read from a companion JSON file if needed
    """
    # Get base filename without path and extension
    base = os.path.basename(blob_name)
    name_without_ext = os.path.splitext(base)[0]
    
    # Convert filename to readable title
    # Example: "1730923200-video" -> "Daily News Short"
    title = name_without_ext.replace("_", " ").replace("-", " ").strip()
    if not title or title.isdigit():
        title = "Daily News Short"
    
    # Default description with hashtags
    description = f"{title}\n\nStay informed with our daily news shorts.\n\n#news #shorts #breaking #politics #dailynews"
    
    # Tags for YouTube
    tags = ["news", "shorts", "breaking news", "politics", "daily news"]
    
    return title, description, tags

def gcs_to_social(event, context):
    """
    Cloud Function entry point
    Triggered when a file is uploaded to Google Cloud Storage
    
    Args:
        event (dict): Event payload
        context (google.cloud.functions.Context): Metadata
    """
    print("="*60)
    print("Cloud Function triggered!")
    print("="*60)
    
    # Get bucket and file info from event
    bucket = event["bucket"]
    blob_name = event["name"]
    
    print(f"Bucket: {bucket}")
    print(f"File: {blob_name}")
    
    # Only process files in the "incoming/" folder
    if not blob_name.startswith("incoming/"):
        print(f"Skipping {blob_name} (not in incoming/ folder)")
        return
    
    # Skip if it's a folder/directory marker
    if blob_name.endswith("/"):
        print("Skipping directory marker")
        return
    
    try:
        # Download video from GCS
        local_path = _download_from_gcs(bucket, blob_name)
        
        # Derive metadata
        title, description, tags = _derive_metadata(bucket, blob_name)
        
        print(f"\nMetadata:")
        print(f"  Title: {title}")
        print(f"  Description: {description[:100]}...")
        print(f"  Tags: {tags}")
        
        # Upload to YouTube
        print("\n" + "-"*60)
        yt_video_id = _upload_youtube(local_path, title, description, tags)
        
        # Small random delay before Facebook (avoid simultaneous posts)
        delay = random.randint(10, 30)
        print(f"\nWaiting {delay} seconds before Facebook upload...")
        time.sleep(delay)
        
        # Upload to Facebook
        print("-"*60)
        fb_video_id = _upload_facebook(local_path, description)
        
        # Clean up temp file
        os.remove(local_path)
        
        # Log success
        result = {
            "status": "success",
            "youtube_video_id": yt_video_id,
            "youtube_url": f"https://youtube.com/shorts/{yt_video_id}",
            "facebook_video_id": fb_video_id,
            "source_file": blob_name
        }
        
        print("\n" + "="*60)
        print("✅ SUCCESS!")
        print("="*60)
        print(json.dumps(result, indent=2))
        
        return result
        
    except Exception as e:
        print("\n" + "="*60)
        print("❌ ERROR!")
        print("="*60)
        print(f"Error: {str(e)}")
        
        # Log error but don't raise (Cloud Functions will retry on exceptions)
        error_result = {
            "status": "error",
            "error": str(e),
            "source_file": blob_name
        }
        print(json.dumps(error_result, indent=2))
        
        # Re-raise to trigger Cloud Functions retry logic
        raise
