"""
Google Cloud Function: Automatically post videos to YouTube Shorts + Facebook
Triggers when a new video is uploaded to Google Cloud Storage
"""

from pathlib import Path

from google.cloud import storage

import os
import tempfile
import time
import random
import json
from google.cloud import storage, secretmanager
from google.api_core.exceptions import NotFound
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError, ResumableUploadError
import requests

# Get project ID from environment (auto-injected by Cloud Functions)
PROJECT_ID = os.environ.get("GCP_PROJECT")

def _get_secret(name: str) -> str:
    """Retrieve secret from Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()
    path = client.secret_version_path(PROJECT_ID, name, "latest")
    response = client.access_secret_version(request={"name": path})
    return response.payload.data.decode()

    
def _maybe_download_companion_metadata(bucket: str, blob_name: str) -> dict | None:
    """If a companion JSON file exists (same base name with .json) download and parse it."""
    if not blob_name.endswith(".mp4"):
        return None
    base_no_ext = os.path.splitext(blob_name)[0]
    meta_blob_name = base_no_ext + ".json"
    client = storage.Client()
    bucket_obj = client.bucket(bucket)
    meta_blob = bucket_obj.blob(meta_blob_name)
    
    print(f"DEBUG: Looking for companion metadata: {meta_blob_name}")
    
    if not meta_blob.exists():
        print(f"DEBUG: No companion JSON found at {meta_blob_name}")
        return None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        meta_blob.download_to_filename(tmp)
        data = json.loads(Path(tmp).read_text(encoding="utf-8"))
        os.remove(tmp)
        if isinstance(data, dict):
            print(f"DEBUG: Found companion metadata JSON: {meta_blob_name}")
            print(f"DEBUG:   Title: {data.get('title', 'N/A')}")
            print(f"DEBUG:   Description: {data.get('description', 'N/A')[:100]}...")
            print(f"DEBUG:   Tags: {data.get('tags', [])}")
            return data
        else:
            print(f"DEBUG: Companion JSON is not a dict, ignoring")
            return None
    except Exception as e:
        print(f"DEBUG: Failed to read companion metadata: {e}")
        return None

def _derive_metadata(bucket: str, blob_name: str) -> tuple:
    """Return (title, description, tags) preferring companion JSON over heuristics."""
    meta = _maybe_download_companion_metadata(bucket, blob_name)
    if meta:
        title = (meta.get("title") or "Daily News Update").strip()[:100]
        description = (meta.get("description") or title)[:4900]
        tags = meta.get("tags") or ["news", "politics", "shorts", "breaking"]
        return title, description, tags

    base = os.path.basename(blob_name)
    stem = os.path.splitext(base)[0]
    cleaned = stem.replace("news_video", "").replace("_", " ").strip()
    if cleaned.isdigit() or len(cleaned) < 4:
        cleaned = "Daily News Update"
    title = cleaned[:100]
    description = f"{title}\n\nStay informed with our daily news shorts.\n\n#news #shorts #politics #dailynews"
    tags = ["news", "politics", "shorts", "daily news"]
    return title, description, tags
def _try_get_secret(name: str):
    """Return secret value or None if it doesn't exist."""
    try:
        return _get_secret(name)
    except NotFound:
        return None

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
    """Upload video to YouTube as a Short
    
    Raises:
        Exception: For upload limit exceeded or other YouTube API errors
    """
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
    
    # Execute resumable upload with error handling
    try:
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Upload {int(status.progress() * 100)}% complete")
        
        video_id = response.get("id")
        print(f"✅ YouTube upload complete: https://youtube.com/shorts/{video_id}")
        
        return video_id
        
    except (HttpError, ResumableUploadError) as e:
        error_str = str(e)
        # Check for upload limit exceeded
        if 'uploadLimitExceeded' in error_str or 'exceeded the number of videos' in error_str:
            print(f"⚠️ YouTube upload limit exceeded. Channel needs verification or has hit daily quota.")
            print(f"   Error details: {error_str}")
            raise Exception("YouTube upload limit exceeded") from e
        else:
            print(f"❌ YouTube API error: {error_str}")
            raise

def _upload_facebook(filepath: str, title: str, description: str) -> str:
    """Upload video to Facebook Page"""
    print(f"Uploading to Facebook")
    
    page_id = _get_secret("FB_PAGE_ID")
    token = _get_secret("FB_PAGE_TOKEN")
    
    # Facebook Graph API endpoint for video upload
    url = f"https://graph-video.facebook.com/v19.0/{page_id}/videos"
    
    # Create a formatted message with title and description (Facebook surfaces description; keep title separately)
    message = f"{title}\n\n{description}" if title and description else (title or description or "Daily news update")
    
    # Upload video file
    with open(filepath, "rb") as video_file:
        response = requests.post(
            url,
            data={
                "access_token": token,
                "description": message,
                "title": title[:100],  # Provide explicit title
                "published": "true"   # Ensure the video is published (not unpublished/draft)
            },
            files={"source": video_file},
            timeout=300  # 5 minute timeout for large files
        )

    if not response.ok:
        print(f"Facebook response status: {response.status_code}")
        request_id = response.headers.get('x-fb-trace-id') or response.headers.get('x-fb-rev')
        if request_id:
            print(f"Facebook request trace id: {request_id}")
        print(f"Facebook response headers (truncated): { {k: v for k, v in list(response.headers.items())[:10]} }")
        try:
            print(f"Facebook error body: {response.json()}")
        except Exception:
            print(f"Facebook error text: {response.text[:500]}")
        # Raise after logging details
        response.raise_for_status()

    video_id = None
    try:
        data = response.json()
        video_id = data.get("id")
    except Exception as parse_err:
        print(f"WARNING: Could not parse Facebook JSON response: {parse_err}")

    print(f"✅ Facebook upload complete: Video ID {video_id}")
    return video_id

def _facebook_preflight(token: str) -> dict:
    """Validate Facebook token and permissions; return dict with status info."""
    base = "https://graph.facebook.com/v19.0"
    info = {"token_valid": False, "missing_perms": [], "perms": [], "error": None}
    try:
        # First check if token works at all
        me = requests.get(f"{base}/me", params={"access_token": token}, timeout=15)
        if me.ok:
            info["token_valid"] = True
        else:
            print(f"FB preflight /me failed: {me.status_code}")
            try: 
                error_data = me.json()
                print(f"Error: {error_data}")
                info["error"] = error_data.get("error", {}).get("message", "Unknown error")
            except Exception: 
                print(me.text[:300])
                info["error"] = me.text[:300]
            return info  # Don't continue if basic validation fails
            
        # Check permissions
        perms = requests.get(f"{base}/me/permissions", params={"access_token": token}, timeout=15)
        if perms.ok:
            data = perms.json().get("data", [])
            granted = [p["permission"] for p in data if p.get("status") == "granted"]
            info["perms"] = granted
            required = ["pages_manage_posts", "pages_read_engagement", "publish_video"]
            info["missing_perms"] = [r for r in required if r not in granted]
        else:
            print(f"FB preflight /me/permissions failed: {perms.status_code}")
            try: 
                print(perms.json())
            except Exception: 
                print(perms.text[:300])
    except Exception as e:
        print(f"FB preflight exception: {e}")
        info["error"] = str(e)
    return info


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
    
    # Only process metadata JSON files
    if not blob_name.endswith(".json"):
        print(f"Ignoring non-json object: {blob_name}")
        return "", 204

    import os
    video_id = os.path.splitext(os.path.basename(blob_name))[0]

    # Idempotency: create posted/{video_id}.lock marker
    from caption_utils import _create_post_marker_or_skip, _load_json, _ensure_caption, _build_caption
    if not _create_post_marker_or_skip(bucket, video_id):
        print(f"[idempotency] marker exists for {video_id}; skipping post")
        return "", 200
    
    try:
        # Load metadata JSON
        meta = _load_json(bucket, blob_name)
        parts = _ensure_caption(meta)
        caption = _build_caption(parts)

        # Resolve video object path (same stem, .mp4)
        video_object = f"{os.path.dirname(blob_name)}/{video_id}.mp4" if "/" in blob_name else f"{video_id}.mp4"

        # Download video to temp
        local_path = _download_from_gcs(bucket, video_object)

        # Post to Facebook (once only)
        fb_video_id = None
        fb_success = False
        fb_page_id = _try_get_secret("FB_PAGE_ID")
        fb_page_token = _try_get_secret("FB_PAGE_TOKEN")
        if fb_page_id and fb_page_token:
            print("\nFacebook token preflight...")
            fb_info = _facebook_preflight(fb_page_token)
            print(f"FB token valid: {fb_info['token_valid']} | Granted perms: {fb_info['perms']}")
            if not fb_info['token_valid']:
                print("❌ Facebook token is INVALID!")
                print(f"   Error: {fb_info.get('error', 'Unknown error')}")
                print("   Skipping Facebook upload.")
            elif fb_info['missing_perms']:
                print(f"⚠️ Missing required permissions: {fb_info['missing_perms']}")
                print("   Upload may fail. Please regenerate token with all required scopes.")
                delay = random.randint(10, 30)
                print(f"\nWaiting {delay} seconds before Facebook upload...")
                time.sleep(delay)
                print("-"*60)
                try:
                    fb_video_id = _upload_facebook(local_path, parts["title"], parts["description"])
                    fb_success = True
                except Exception as fb_err:
                    print(f"❌ Facebook upload failed: {fb_err}")
            else:
                delay = random.randint(10, 30)
                print(f"\nWaiting {delay} seconds before Facebook upload...")
                time.sleep(delay)
                print("-"*60)
                try:
                    fb_video_id = _upload_facebook(local_path, parts["title"], parts["description"])
                    fb_success = True
                except Exception as fb_err:
                    print(f"❌ Facebook upload failed: {fb_err}")
        else:
            missing = []
            if not fb_page_id:
                missing.append("FB_PAGE_ID")
            if not fb_page_token:
                missing.append("FB_PAGE_TOKEN")
            print(f"Skipping Facebook upload (missing secrets: {', '.join(missing)})")

        # Clean up temp file
        os.remove(local_path)

        # Log posting status
        marker_status = "created" if fb_success else "exists"
        print(f"[posted] video_id={video_id} marker={marker_status} title={parts['title'][:80]!r}")
        return "", 200

    except Exception as e:
        print("\n" + "="*60)
        print("❌ ERROR!")
        print("="*60)
        print(f"Error: {str(e)}")
        error_result = {
            "status": "error",
            "error": str(e),
            "source_file": blob_name
        }
        print(json.dumps(error_result, indent=2))
        raise
