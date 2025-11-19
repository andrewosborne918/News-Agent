# main.py
from caption_utils import get_title_description_tags
import os
import json
import tempfile
import traceback
import logging
from typing import Dict, Any, List, Tuple, Optional
import re
import datetime # <<< ADDED for Signed URL expiration

import requests 

from google.cloud import storage, secretmanager
from google.api_core.exceptions import NotFound, Conflict, PreconditionFailed

# --- NEW IMPORTS FOR YOUTUBE ---
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, ResumableUploadError
from google.auth.transport import requests as google_auth_requests
# -------------------------------

import functions_framework

_SECRET_CACHE: Dict[str, str] = {}

logger = logging.getLogger(__name__)
PROJECT_ID = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")


def _get_secret(secret_name: str) -> Optional[str]:
    """Fetch a secret from Secret Manager (cached). Returns None if unavailable."""
    global _SECRET_CACHE
    if secret_name in _SECRET_CACHE:
        return _SECRET_CACHE[secret_name]

    if not PROJECT_ID:
        logger.error("GCP_PROJECT environment variable not set. Cannot fetch secrets.")
        return None

    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("utf-8").strip()
        
        if not secret_value:
            logger.warning(f"Secret {secret_name} is empty.")
            return None
            
        _SECRET_CACHE[secret_name] = secret_value
        logger.info(f"Successfully loaded secret: {secret_name}")
        return secret_value
    except Exception as e:
        logger.exception(f"Could not load secret {secret_name}: {e}")
        return None


@functions_framework.cloud_event
def gcs_to_social(event):
    """Cloud Storage (GCS) trigger for new/changed objects."""
    data = event.data or {}
    bucket = data.get("bucket")
    name = data.get("name")

    # Only trigger on the .json metadata file
    if not bucket or not name or not name.startswith("incoming/") or not name.endswith(".json"):
        print(f"skip: not an incoming metadata JSON -> bucket={bucket} name={name}")
        return

    # 1. Check if job is already done (Idempotency)
    if _marker_exists(bucket, name, ".posted"):
        print(f"skip: already posted (marker file exists) -> {name}")
        return
        
    if _marker_exists(bucket, name, ".failed"):
        print(f"skip: already failed (marker file exists) -> {name}")
        return

    # 2. Check if job is currently running (Locking)
    if _marker_exists(bucket, name, ".processing"):
        print(f"skip: currently processing (lock file exists) -> {name}")
        return

    # 3. Set Lock
    _create_post_marker(bucket, name, ".processing", "Processing started")

    try:
        msg, _status = _process_metadata_json(bucket, name)
        print(msg)
    finally:
        # 4. Release Lock (Always cleanup the .processing file)
        _delete_marker(bucket, name, ".processing")


def _download_gcs_to_tempfile(bucket_name: str, blob_name: str) -> str:
    """Download gs://bucket/blob to a local temp file and return the local path."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    _, ext = os.path.splitext(blob_name)
    fd, tmp = tempfile.mkstemp(suffix=ext or ".bin")
    os.close(fd)
    blob.download_to_filename(tmp)
    return tmp


def _marker_exists(bucket_name: str, json_blob_name: str, suffix: str) -> bool:
    """Check if a marker file like <base>.posted or <base>.failed exists."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    base_no_ext = os.path.splitext(json_blob_name)[0]
    marker_key = f"{base_no_ext}{suffix}"
    marker_blob = bucket.blob(marker_key)
    return marker_blob.exists()


def _create_post_marker(bucket_name: str, json_blob_name: str, suffix: str, content: str = ""):
    """Create an idempotency marker <base>.posted, <base>.failed, or <base>.processing."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    base_no_ext = os.path.splitext(json_blob_name)[0]
    marker_key = f"{base_no_ext}{suffix}"
    marker_blob = bucket.blob(marker_key)
    try:
        marker_blob.upload_from_string(
            data=content.encode("utf-8"),
            content_type="text/plain",
        )
        print(f"[marker] created marker {marker_key}")
    except Exception as e:
        print(f"[marker] ERROR: failed to create marker {marker_key}: {e}")

def _delete_marker(bucket_name: str, json_blob_name: str, suffix: str):
    """Delete a marker file (used for cleaning up .processing lock)."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    base_no_ext = os.path.splitext(json_blob_name)[0]
    marker_key = f"{base_no_ext}{suffix}"
    marker_blob = bucket.blob(marker_key)
    try:
        if marker_blob.exists():
            marker_blob.delete()
            print(f"[marker] deleted marker {marker_key}")
    except Exception as e:
        print(f"[marker] warning: failed to delete marker {marker_key}: {e}")

def _load_json(bucket_name: str, json_blob_name: str) -> Dict[str, Any]:
    """Download and parse a companion JSON from GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(json_blob_name)
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        blob.download_to_filename(tmp)
        with open(tmp, "r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

# --- NEW: Helper to generate Signed URL ---
def _generate_signed_url(bucket_name: str, blob_name: str) -> str:
    """Generates a V4 Signed URL valid for 1 hour to allow Make.com to download the video."""
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Requires 'Service Account Token Creator' role on the Service Account
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=60), # 60 minutes validity
            method="GET",
        )
        return url
    except Exception as e:
        logger.error(f"[gcs] Failed to generate signed URL: {e}")
        raise

# --- UPDATED: Send Signed URL + Metadata to Make ---
def _trigger_make_tiktok_scenario(video_url: str, description: str, title: str):
    """
    Sends the GCS Signed URL and metadata to Make.com.
    """
    logger.info("[make] Attempting to trigger Make.com scenario...")
    
    webhook_url = _get_secret("MAKE_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("[make] MAKE_WEBHOOK_URL secret is missing. Skipping Make.com trigger.")
        return

    payload = {
        "video_url": video_url,  # This is the direct file link (Signed URL)
        "caption": description,
        "title": title
    }

    try:
        response = requests.post(
            webhook_url, 
            json=payload, 
            timeout=15 
        )
        response.raise_for_status() 
        logger.info(f"[make] Webhook successfully triggered. Status: {response.status_code}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"[make] Failed to trigger Make.com webhook: {e}")


def _process_metadata_json(bucket_name: str, json_blob_name: str) -> tuple[str, int]:
    """
    Reads companion JSON, determines post type, generates captions, 
    triggers Make.com (for TikTok), then uploads to YouTube and Facebook.
    """
    print("Processor invoked")
    print("============================================================")
    print(f"Bucket: {bucket_name}")
    print(f"JSON:   {json_blob_name}")

    # Load JSON
    try:
        meta = _load_json(bucket_name, json_blob_name)
    except Exception as e:
        print(f"ERROR: failed to load metadata JSON: {e}")
        _create_post_marker(bucket_name, json_blob_name, ".failed", f"Failed to load JSON: {e}")
        return ("failed to load metadata", 200) 

    # --- Determine Post Type ---
    post_type = meta.get("post_type", "video") 
    base_no_ext = os.path.splitext(json_blob_name)[0]
    
    # Use get_title_description_tags for robust AI-powered caption generation
    try:
        title, description, tags = get_title_description_tags(meta)
        logger.info("[caption] Successfully generated captions.")
    except Exception as e:
        logger.exception("ERROR: get_title_description_tags failed: %s", e)
        _create_post_marker(bucket_name, json_blob_name, ".failed", f"Failed to generate captions: {e}")
        return ("failed to generate captions", 200)

    fb_image_caption = description
    fb_video_description = f"{title}\n\n{description}"

    local_media_path = None
    try:
        if post_type == "image":
            # ... (Image logic remains the same) ...
            media_blob_name = None
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            
            for ext in [".png", ".jpg", ".jpeg", ".webp"]:
                potential_name = f"{base_no_ext}{ext}"
                if bucket.blob(potential_name).exists():
                    media_blob_name = potential_name
                    break
            
            if not media_blob_name:
                raise FileNotFoundError(f"Could not find matching image for {json_blob_name}")
            
            local_media_path = _download_gcs_to_tempfile(bucket_name, media_blob_name)
            print(f"Uploading to Facebook (Image): {local_media_path}")
            _upload_facebook_image(local_media_path, fb_image_caption)
            print("[facebook] done")

        else: # Video processing
            media_blob_name = base_no_ext + ".mp4"
            print(f"  Video candidate: {media_blob_name}")

            # --- STEP 1: TRIGGER MAKE.COM (TIKTOK) FIRST ---
            # We do this BEFORE downloading/uploading to YouTube/Facebook.
            # This uses a Signed URL so Make/Buffer can download the file directly.
            try:
                print("[make] Generating signed URL for Make.com...")
                signed_url = _generate_signed_url(bucket_name, media_blob_name)
                print(f"[make] Triggering webhook...")
                _trigger_make_tiktok_scenario(signed_url, fb_video_description, title)
                print("[make] done")
            except Exception as make_e:
                print(f"[make] WARNING: Failed to trigger TikTok flow: {make_e}")
                # We continue execution so YouTube/FB still happen even if Make fails
            
            # --- STEP 2: DOWNLOAD FOR YOUTUBE/FB ---
            local_media_path = _download_gcs_to_tempfile(bucket_name, media_blob_name)
            
            # --- STEP 3: UPLOAD TO YOUTUBE ---
            print(f"Uploading to YouTube (Video): {local_media_path}")
            _upload_youtube(local_media_path, title, description, tags)
            print("[youtube] done")

            # --- STEP 4: UPLOAD TO FACEBOOK ---
            print(f"Uploading to Facebook (Video): {local_media_path}")
            _upload_facebook_video(local_media_path, title, fb_video_description) 
            print("[facebook] done")
        
        _create_post_marker(bucket_name, json_blob_name, ".posted", "Success")
        
    except Exception as e:
        print(f"ERROR: publish failed: {e}\n{traceback.format_exc()}")
        _create_post_marker(bucket_name, json_blob_name, ".failed", f"Publish failed: {e}\n{traceback.format_exc()}")
    finally:
        try:
            if local_media_path and os.path.exists(local_media_path):
                os.remove(local_media_path)
                print(f"Cleaned up temp file: {local_media_path}")
        except Exception:
            pass

    return (f"ok: processed {json_blob_name}", 200)

def _upload_youtube(local_filename: str, title: str, description: str, tags: list[str] | None = None) -> str:
    """Uploads a video to YouTube from a local file path. Returns the video ID."""
    logger.info("[youtube] Starting YouTube upload...")
    creds_json_str = _get_secret("YOUTUBE_CREDENTIALS_JSON")
    if not creds_json_str:
        logger.error("[youtube] FATAL: YOUTUBE_CREDENTIALS_JSON secret is missing.")
        raise Exception("YOUTUBE_CREDENTIALS_JSON secret is missing.")

    try:
        creds_data = json.loads(creds_json_str)
        creds = Credentials(
            token=None,
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=["https://www.googleapis.com/auth/youtube.upload"]
        )
        
        creds.refresh(google_auth_requests.Request())
        
        youtube = build("youtube", "v3", credentials=creds)
        
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or ["news", "politics"],
                "categoryId": "25" # 25 = News & Politics
            },
            "status": {
                "privacyStatus": "public" # Set to public
            }
        }

        media = MediaFileUpload(local_filename, chunksize=-1, resumable=True)
        
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"[youtube] Uploaded {int(status.progress() * 100)}%")
            except HttpError as e:
                logger.error(f"[youtube] HTTP error: {e}")
                raise
            except ResumableUploadError as e:
                logger.error(f"[youtube] Resumable upload error: {e}")
                raise

        logger.info(f"[youtube] Upload successful! Video ID: {response['id']}")
        return response['id'] 

    except Exception as e:
        logger.exception(f"[youtube] Failed to upload: {e}")
        raise 

def _upload_facebook_video(local_filename: str, title: str, description: str):
    """
    Uploads a VIDEO to Facebook from a local file path.
    Includes sanitization to prevent 400 Bad Request errors.
    """
    logger.info("[facebook] Starting Facebook VIDEO upload...")
    
    # --- SANITIZATION STEP ---
    sanitized_title = re.sub(r'[^\w\s\-\.\,\!\?\(\)\&\/\:\;]+', '', title).strip() 
    sanitized_description = re.sub(r'[^\w\s\-\.\,\!\?\(\)\&\/\:\;]+', '', description).strip()
    
    logger.info(f"[facebook] Posting with sanitized title: {sanitized_title[:50]}...")
    # --- END SANITIZATION ---
    
    page_token = _get_secret("FACEBOOK_PAGE_TOKEN")
    page_id = _get_secret("FB_PAGE_ID")
    
    if not page_token or not page_id:
        logger.error("[facebook] FATAL: FACEBOOK_PAGE_TOKEN or FB_PAGE_ID secrets are missing.")
        raise Exception("FACEBOOK_PAGE_TOKEN or FB_PAGE_ID secrets are missing.")

    url = f"https://graph-video.facebook.com/v20.0/{page_id}/videos"
    
    params = {
        "access_token": page_token,
        "description": sanitized_description, 
        "title": sanitized_title             
    }

    try:
        with open(local_filename, 'rb') as f:
            files = {
                'source': (os.path.basename(local_filename), f, 'video/mp4')
            }
            response = requests.post(url, params=params, files=files, timeout=900) 
            
        response_data = response.json()
        
        if response.status_code == 200 and "id" in response_data:
            logger.info(f"[facebook] Video upload successful! Video ID: {response_data['id']}")
        else:
            logger.error(f"[facebook] Video upload failed. Status: {response.status_code}, Response: {response_data}")
            raise Exception(f"Facebook video upload failed: {response_data}")

    except Exception as e:
        logger.exception(f"[facebook] Failed to upload video: {e}")
        raise

def _upload_facebook_image(local_filename: str, caption: str):
    """Uploads an IMAGE to Facebook from a local file path."""
    logger.info("[facebook] Starting Facebook IMAGE upload...")
    
    page_token = _get_secret("FACEBOOK_PAGE_TOKEN")
    page_id = _get_secret("FB_PAGE_ID")
    
    if not page_token or not page_id:
        logger.error("[facebook] FATAL: FACEBOOK_PAGE_TOKEN or FB_PAGE_ID secrets are missing.")
        raise Exception("FACEBOOK_PAGE_TOKEN or FB_PAGE_ID secrets are missing.")

    url = f"https://graph.facebook.com/v20.0/{page_id}/photos"
    
    # Sanitization for image caption
    sanitized_caption = re.sub(r'[^\w\s\-\.\,\!\?\(\)\&\/\:\;]+', '', caption).strip() 
    
    params = {
        "access_token": page_token,
        "caption": sanitized_caption, 
    }

    try:
        with open(local_filename, 'rb') as f:
            files = {
                'source': (os.path.basename(local_filename), f, 'image/jpeg')
            }
            response = requests.post(url, params=params, files=files, timeout=300) 
            
        response_data = response.json()
        
        if response.status_code == 200 and "id" in response_data:
            logger.info(f"[facebook] Image post successful! Post ID: {response_data['id']}")
        else:
            logger.error(f"[facebook] Image post failed. Status: {response.status_code}, Response: {response_data}")
            raise Exception(f"Facebook image post failed: {response_data}")

    except Exception as e:
        logger.exception(f"[facebook] Failed to post image: {e}")
        raise