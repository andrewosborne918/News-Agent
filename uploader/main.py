# main.py
from caption_utils import get_title_description_tags
import os
import json
import tempfile
import traceback
import logging
from typing import Dict, Any, List, Tuple, Optional

import requests # <-- Already here, but needed for Facebook

from google.cloud import storage, secretmanager
from google.api_core.exceptions import NotFound, Conflict, PreconditionFailed

# --- NEW IMPORTS FOR YOUTUBE ---
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, ResumableUploadError
# -------------------------------

import functions_framework

# --- NEW: SECRET MANAGER CACHE ---
_SECRET_CACHE: Dict[str, str] = {}
# ---------------------------------

logger = logging.getLogger(__name__)
PROJECT_ID = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")


# --- NEW: GENERIC SECRET LOADER ---
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
        return secret_value
    except Exception as e:
        logger.exception(f"Could not load secret {secret_name}: {e}")
        return None
# ----------------------------------


@functions_framework.cloud_event
def gcs_to_social(event):
    """Cloud Storage (GCS) trigger for new/changed objects."""
    data = event.data or {}
    bucket = data.get("bucket")
    name = data.get("name")

    # Only process companion JSON files; ignore everything else
    if not bucket or not name or not name.endswith(".json"):
        print(f"skip: not a metadata JSON -> bucket={bucket} name={name}")
        return

    # --- ADDED: Check for marker file ---
    # This prevents the function from re-running if you edit the .json file
    if _marker_exists(bucket, name, ".posted"):
        print(f"skip: already posted (marker file exists) -> {name}")
        return
    # ------------------------------------

    msg, _status = _process_metadata_json(bucket, name)
    print(msg)

print("[startup] cwd:", os.getcwd())
print("[startup] dir contents:", os.listdir(os.path.dirname(__file__)))


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
    """Create an idempotency marker <base>.posted or <base>.failed."""
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


def _process_metadata_json(bucket_name: str, json_blob_name: str) -> tuple[str, int]:
    """
    Reads companion JSON, ensures caption present, and kicks off publishing.
    Returns (message, http_status).
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
        return ("failed to load metadata", 200) # Return 200 to stop GCS retries

    # Use get_title_description_tags for robust AI-powered caption generation
    try:
        title, description, tags = get_title_description_tags(meta)
        logger.info("[caption] Successfully generated captions.")
        logger.info(f"[caption] Title: {title}")
        logger.info(f"[caption] Run ID: {meta.get('run_id')}")
    except Exception as e:
        logger.exception("ERROR: get_title_description_tags failed: %s", e)
        _create_post_marker(bucket_name, json_blob_name, ".failed", f"Failed to generate captions: {e}")
        return ("failed to generate captions", 200)

    # Pick the .mp4 that matches the JSON (same prefix)
    base_no_ext = os.path.splitext(json_blob_name)[0]
    video_blob_name = base_no_ext + ".mp4"
    print(f"  Video candidate: {video_blob_name}")

    local_video_path = None
    try:
        # Download video to a local temp file
        local_video_path = _download_gcs_to_tempfile(bucket_name, video_blob_name)
        
        print(f"Uploading to YouTube (local): {local_video_path}")
        _upload_youtube(local_video_path, title, description, tags)
        print("[youtube] done")

        print(f"Uploading to Facebook (local): {local_video_path}")
        _upload_facebook(local_video_path, title, description)
        print("[facebook] done")
        
        # If all successful, create .posted marker
        _create_post_marker(bucket_name, json_blob_name, ".posted", "Success")
        
    except Exception as e:
        print(f"ERROR: publish failed: {e}\n{traceback.format_exc()}")
        _create_post_marker(bucket_name, json_blob_name, ".failed", f"Publish failed: {e}\n{traceback.format_exc()}")
    finally:
        # Clean up the temp video file
        try:
            if local_video_path and os.path.exists(local_video_path):
                os.remove(local_video_path)
                print(f"Cleaned up temp file: {local_video_path}")
        except Exception:
            pass

    return (f"ok: processed {json_blob_name}", 200)

# --- MODIFIED: YOUTUBE UPLOAD ---
def _upload_youtube(local_filename: str, title: str, description: str, tags: list[str] | None = None):
    """Uploads a video to YouTube from a local file path."""
    logger.info("[youtube] Starting YouTube upload...")
    creds_json_str = _get_secret("YOUTUBE_CREDENTIALS_JSON")
    if not creds_json_str:
        logger.error("[youtube] FATAL: YOUTUBE_CREDENTIALS_JSON secret is missing.")
        return

    try:
        creds_data = json.loads(creds_json_str)
        # Assumes secret contains: {"client_id": "...", "client_secret": "...", "refresh_token": "..."}
        creds = Credentials(
            token=None, # No access token, we will refresh
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=["https://www.googleapis.com/auth/youtube.upload"]
        )
        
        # Refresh the token. This is necessary because we only have a refresh token.
        creds.refresh(requests.Request())
        
        youtube = build("youtube", "v3", credentials=creds)
        
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or ["news", "politics"],
                "categoryId": "25" # 25 = News & Politics
            },
            "status": {
                "privacyStatus": "public" # "private", "public", or "unlisted"
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
                if e.resp.status in [401, 403]:
                    logger.error(f"[youtube] Auth error: {e}. Check YOUTUBE_CREDENTIALS_JSON.")
                else:
                    logger.error(f"[youtube] HTTP error: {e}")
                raise
            except ResumableUploadError as e:
                logger.error(f"[youtube] Resumable upload error: {e}")
                raise

        logger.info(f"[youtube] Upload successful! Video ID: {response['id']}")

    except Exception as e:
        logger.exception(f"[youtube] Failed to upload: {e}")
        raise # Re-raise exception to be caught by _process_metadata_json


# --- MODIFIED: FACEBOOK UPLOAD ---
def _upload_facebook(local_filename: str, title: str, description: str):
    """Uploads a video to Facebook from a local file path."""
    logger.info("[facebook] Starting Facebook upload...")
    
    page_token = _get_secret("FACEBOOK_PAGE_TOKEN")
    page_id = _get_secret("FB_PAGE_ID")
    
    if not page_token or not page_id:
        logger.error("[facebook] FATAL: FACEBOOK_PAGE_TOKEN or FB_PAGE_ID secrets are missing.")
        return

    # Use the simple (non-resumable) upload endpoint
    url = f"https://graph-video.facebook.com/v20.0/{page_id}/videos"
    
    # Facebook uses 'description' for the main text, and 'title' for the video title
    fb_description = f"{title}\n\n{description}"
    
    params = {
        "access_token": page_token,
        "description": fb_description,
        "title": title
        # "published": "true" # Defaults to true. Use "false" to upload as a draft.
    }

    try:
        with open(local_filename, 'rb') as f:
            files = {
                'source': (os.path.basename(local_filename), f, 'video/mp4')
            }
            
            response = requests.post(url, params=params, files=files, timeout=900) # 15 min timeout
            
        response_data = response.json()
        
        if response.status_code == 200 and "id" in response_data:
            logger.info(f"[facebook] Upload successful! Video ID: {response_data['id']}")
        else:
            logger.error(f"[facebook] Upload failed. Status: {response.status_code}, Response: {response_data}")
            raise Exception(f"Facebook upload failed: {response_data}")

    except Exception as e:
        logger.exception(f"[facebook] Failed to upload: {e}")
        raise # Re-raise exception to be caught by _process_metadata_json