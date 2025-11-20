# uploader/main.py
from caption_utils import get_title_description_tags
import os
import json
import tempfile
import traceback
import logging
from typing import Dict, Any, Optional, List
import re
import datetime
import requests

from google.cloud import storage, secretmanager
from google.api_core.exceptions import NotFound, Conflict, PreconditionFailed
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, ResumableUploadError
from google.auth.transport import requests as google_auth_requests
import functions_framework

_SECRET_CACHE: Dict[str, str] = {}

logger = logging.getLogger(__name__)
PROJECT_ID = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")


def _get_secret(secret_name: str) -> Optional[str]:
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

    if _marker_exists(bucket, name, ".posted"):
        print(f"skip: already posted (marker file exists) -> {name}")
        return
    if _marker_exists(bucket, name, ".failed"):
        print(f"skip: already failed (marker file exists) -> {name}")
        return

    if _marker_exists(bucket, name, ".processing"):
        print(f"skip: currently processing (lock file exists) -> {name}")
        return

    _create_post_marker(bucket, name, ".processing", "Processing started")

    try:
        msg, _status = _process_metadata_json(bucket, name)
        print(msg)
    finally:
        _delete_marker(bucket, name, ".processing")


def _download_gcs_to_tempfile(bucket_name: str, blob_name: str) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    _, ext = os.path.splitext(blob_name)
    fd, tmp = tempfile.mkstemp(suffix=ext or ".bin")
    os.close(fd)
    blob.download_to_filename(tmp)
    return tmp


def _marker_exists(bucket_name: str, json_blob_name: str, suffix: str) -> bool:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    base_no_ext = os.path.splitext(json_blob_name)[0]
    marker_key = f"{base_no_ext}{suffix}"
    marker_blob = bucket.blob(marker_key)
    return marker_blob.exists()


def _create_post_marker(bucket_name: str, json_blob_name: str, suffix: str, content: str = ""):
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


def _generate_signed_url(bucket_name: str, blob_name: str) -> str:
    """Generates a V4 Signed URL valid for 60 minutes."""
    logger.info(f"[gcs] Generating signed URL for {bucket_name}/{blob_name}")
    client = storage.Client()  # uses Cloud Run's service account
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    if not blob.exists():
        raise FileNotFoundError(f"Blob not found for signed URL: {bucket_name}/{blob_name}")

    try:
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=60),
            method="GET",
        )
        logger.info("[gcs] Signed URL generated successfully")
        return url
    except Exception as e:
        logger.exception(f"[gcs] Failed to generate signed URL: {e}")
        raise


def _trigger_make_tiktok_scenario(video_url: str, thumbnail_url: str, description: str, title: str):
    """
    Sends the GCS Signed URLs and metadata to Make.com.
    """
    logger.info("[make] Attempting to trigger Make.com scenario...")
    webhook_url = _get_secret("MAKE_WEBHOOK_URL")

    logger.info(f"DEBUG: [make] Retrieved Webhook URL (starts): {webhook_url[:10]}..." if webhook_url else
                "DEBUG: [make] Webhook URL is None or empty.")

    if not webhook_url:
        logger.error("❌ [make] MAKE_WEBHOOK_URL is EMPTY. Cannot proceed.")
        raise ValueError("MAKE_WEBHOOK_URL is missing or empty.")

    payload = {
        "video_url": video_url,
        "thumbnail_url": thumbnail_url,
        "caption": description,
        "title": title,
    }

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        logger.info(
            f"✅ [make] Webhook triggered. Status: {response.status_code}. "
            f"Response: {response.text[:100]}..."
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ [make] Webhook CRASHED. Error Type: {type(e).__name__}. Message: {e}")
        raise e


def _process_metadata_json(bucket_name: str, json_blob_name: str) -> tuple[str, int]:
    print("Processor invoked")
    print(f"Bucket: {bucket_name} | JSON: {json_blob_name}")

    try:
        meta = _load_json(bucket_name, json_blob_name)
    except Exception as e:
        _create_post_marker(bucket_name, json_blob_name, ".failed", f"Failed to load JSON: {e}")
        return ("failed to load metadata", 200)

    try:
        title, description, tags = get_title_description_tags(meta)
        logger.info("[caption] Successfully generated captions.")
    except Exception as e:
        _create_post_marker(bucket_name, json_blob_name, ".failed", f"Failed to generate captions: {e}")
        return ("failed to generate captions", 200)

    post_type = meta.get("post_type", "video")
    base_no_ext = os.path.splitext(json_blob_name)[0]
    fb_video_description = f"{title}\n\n{description}"
    local_media_path = None

    try:
        if post_type == "image":
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

            fb_image_caption = fb_video_description  # simple reuse so variable exists
            print(f"Uploading to Facebook (Image): {local_media_path}")
            _upload_facebook_image(local_media_path, fb_image_caption)
            print("[facebook] done")

        else:  # Video processing
            media_blob_name = base_no_ext + ".mp4"
            thumbnail_blob_name = base_no_ext + ".jpg"
            print(f"  Video candidate: {media_blob_name}")

            # STEP 1: GENERATE SIGNED URLs AND TRIGGER MAKE.COM
            print("[make] Generating signed URL for Make.com...")
            signed_url = _generate_signed_url(bucket_name, media_blob_name)
            thumb_signed_url = ""
            try:
                thumb_signed_url = _generate_signed_url(bucket_name, thumbnail_blob_name)
            except Exception:
                print("[make] WARNING: No thumbnail found or failed to sign.")

            print("[make] Triggering webhook...")
            _trigger_make_tiktok_scenario(signed_url, thumb_signed_url, fb_video_description, title)
            print("[make] Make webhook complete.")

            # STEP 2: DOWNLOAD FOR YOUTUBE/FB
            local_media_path = _download_gcs_to_tempfile(bucket_name, media_blob_name)

            # STEP 3: UPLOAD TO YOUTUBE
            print(f"Uploading to YouTube (Video): {local_media_path}")
            _upload_youtube(local_media_path, title, description, tags)
            print("[youtube] done")

            # STEP 4: UPLOAD TO FACEBOOK
            print(f"Uploading to Facebook (Video): {local_media_path}")
            _upload_facebook_video(local_media_path, title, fb_video_description)
            print("[facebook] done")

        _create_post_marker(bucket_name, json_blob_name, ".posted", "Success")

    except Exception as e:
        print(f"ERROR: publish failed: {e}\n{traceback.format_exc()}")
        _create_post_marker(bucket_name, json_blob_name, ".failed", f"Publish failed: {e}")
    finally:
        if local_media_path and os.path.exists(local_media_path):
            os.remove(local_media_path)

    return (f"ok: processed {json_blob_name}", 200)


def _upload_youtube(local_filename: str, title: str, description: str, tags: Optional[List[str]] = None) -> str:
    logger.info("[youtube] Starting YouTube upload...")
    creds_json_str = _get_secret("YOUTUBE_CREDENTIALS_JSON")
    if not creds_json_str:
        raise Exception("YOUTUBE_CREDENTIALS_JSON secret is missing.")

    try:
        creds_data = json.loads(creds_json_str)
        creds = Credentials(
            token=None,
            refresh_token=creds_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        creds.refresh(google_auth_requests.Request())
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or ["news", "politics"],
                "categoryId": "25",
            },
            "status": {
                "privacyStatus": "public",
            },
        }
        media = MediaFileUpload(local_filename, chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"[youtube] Uploaded {int(status.progress() * 100)}%")

        logger.info(f"[youtube] Upload successful! Video ID: {response['id']}")
        return response["id"]

    except Exception as e:
        logger.exception(f"[youtube] Failed to upload: {e}")
        raise


def _upload_facebook_video(local_filename: str, title: str, description: str):
    logger.info("[facebook] Starting Facebook VIDEO upload...")
    sanitized_title = re.sub(r"[^\w\s\-\.\,\!\?\(\)\&\/\:\;]+", "", title).strip()
    sanitized_description = re.sub(r"[^\w\s\-\.\,\!\?\(\)\&\/\:\;]+", "", description).strip()

    page_token = _get_secret("FACEBOOK_PAGE_TOKEN")
    page_id = _get_secret("FB_PAGE_ID")

    if not page_token or not page_id:
        raise Exception("FACEBOOK_PAGE_TOKEN or FB_PAGE_ID secrets are missing.")

    url = f"https://graph-video.facebook.com/v20.0/{page_id}/videos"
    params = {"access_token": page_token, "description": sanitized_description, "title": sanitized_title}

    try:
        with open(local_filename, "rb") as f:
            files = {"source": (os.path.basename(local_filename), f, "video/mp4")}
            response = requests.post(url, params=params, files=files, timeout=900)

        response_data = response.json()
        if response.status_code != 200 or "id" not in response_data:
            logger.error(
                f"[facebook] Upload failed. Status: {response.status_code}, Response: {response_data}"
            )
            raise Exception(f"Facebook video upload failed: {response_data}")

        logger.info(f"[facebook] Video upload successful! Video ID: {response_data['id']}")

    except Exception as e:
        logger.exception(f"[facebook] Failed to upload video: {e}")
        raise


def _upload_facebook_image(local_filename: str, caption: str):
    logger.info("[facebook] Starting Facebook IMAGE upload...")
    page_token = _get_secret("FACEBOOK_PAGE_TOKEN")
    page_id = _get_secret("FB_PAGE_ID")

    if not page_token or not page_id:
        raise Exception("FACEBOOK_PAGE_TOKEN or FB_PAGE_ID secrets are missing.")

    url = f"https://graph.facebook.com/v20.0/{page_id}/photos"
    sanitized_caption = re.sub(r"[^\w\s\-\.\,\!\?\(\)\&\/\:\;]+", "", caption).strip()
    params = {"access_token": page_token, "caption": sanitized_caption}

    try:
        with open(local_filename, "rb") as f:
            files = {"source": (os.path.basename(local_filename), f, "image/jpeg")}
            response = requests.post(url, params=params, files=files, timeout=300)

        response_data = response.json()
        if response.status_code != 200 or "id" not in response_data:
            logger.error(
                f"[facebook] Image post failed. Status: {response.status_code}, Response: {response_data}"
            )
            raise Exception(f"Facebook image post failed: {response_data}")

        logger.info(f"[facebook] Image post successful! Post ID: {response_data['id']}")

    except Exception as e:
        logger.exception(f"[facebook] Failed to post image: {e}")
        raise
