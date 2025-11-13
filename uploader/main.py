from caption_utils import build_title_and_caption, ensure_caption_dict
import os
import json
import tempfile
import traceback
import logging
from typing import Dict, Any, List, Tuple

import requests

from google.cloud import storage, secretmanager
from google.api_core.exceptions import NotFound, Conflict, PreconditionFailed
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, ResumableUploadError

import functions_framework
# Cloud Event entry point for Cloud Run/Functions Framework
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

    msg, _status = _process_metadata_json(bucket, name)
    print(msg)

# IMPORTANT: caption_utils.py must be in the same folder as main.py
from caption_utils import get_title_description_tags, ensure_caption_dict
print("[startup] cwd:", os.getcwd())
print("[startup] dir contents:", os.listdir(os.path.dirname(__file__)))

logger = logging.getLogger(__name__)
PROJECT_ID = os.environ.get("GCP_PROJECT")


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

def _create_post_marker_or_skip(bucket_name: str, json_blob_name: str) -> bool:
    """
    Create an idempotency marker <base>.posted next to the JSON.
    Returns True if we created the marker (proceed), False if it exists (skip).
    """
    # ...existing code...

def _load_json(bucket_name: str, json_blob_name: str) -> Dict[str, Any]:
    """Download and parse a companion JSON from GCS."""
    # ...existing code...

def _create_post_marker_or_skip(bucket_name: str, json_blob_name: str) -> bool:
    """
    Create an idempotency marker <base>.posted next to the JSON.
    Returns True if we created the marker (should proceed),
    False if it already existed (should skip).
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    base_no_ext = os.path.splitext(json_blob_name)[0]
    marker_key = f"{base_no_ext}.posted"
    marker_blob = bucket.blob(marker_key)
    try:
        marker_blob.upload_from_string(
            data=b"",
            if_generation_match=0,
            content_type="application/octet-stream",
        )
        print(f"[idempotency] created marker {marker_key}")
        return True
    except (Conflict, PreconditionFailed):
        print(f"[idempotency] marker exists {marker_key}; skipping")
        return False

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

    # Idempotency
    if not _create_post_marker_or_skip(bucket_name, json_blob_name):
        return (f"skip: already posted -> {json_blob_name}", 200)

    # Load JSON
    try:
        meta = _load_json(bucket_name, json_blob_name)
    except Exception as e:
        print(f"ERROR: failed to load metadata JSON: {e}")
        return ("failed to load metadata", 200)

    # Ensure fields
    try:
        meta = ensure_caption_dict(meta or {})
    except Exception as e:
        print(f"ERROR: ensure_caption_dict failed: {e}")
        meta = meta or {}
        meta = {
            "title": meta.get("title") or meta.get("Title") or "Update",
            "description": (meta.get("description") or meta.get("Description") or "").strip(),
            "hashtags": meta.get("hashtags") or meta.get("Tags") or [],
        }


    # Use build_title_and_caption for title/caption, and get tags from meta
    try:
        title, caption = build_title_and_caption(meta)
        logger.info("caption type: %s,%s", type(title).__name__, type(caption).__name__)
        tags = meta.get("hashtags", [])
    except Exception as e:
        logger.exception("ERROR: build_title_and_caption failed: %s", e)
        title = (meta.get("title") or meta.get("Title") or "Update").strip()
        caption = (meta.get("description") or meta.get("Description") or "").strip()
        tags = meta.get("hashtags") or meta.get("Tags") or []

    # Pick the .mp4 that matches the JSON (same prefix)
    base_no_ext = os.path.splitext(json_blob_name)[0]
    video_blob_name = base_no_ext + ".mp4"
    print(f"  Video candidate: {video_blob_name}")

    # Download to a local temp file and upload from local path
    local_video_path = _download_gcs_to_tempfile(bucket_name, video_blob_name)
    try:
        print(f"Uploading to YouTube (local): {local_video_path}")
        _upload_youtube(local_video_path, title, caption, tags)
        print("[youtube] done")

        print(f"Uploading to Facebook (local): {local_video_path}")
        _upload_facebook(local_video_path, title, caption)
        print("[facebook] done")
    except Exception as e:
        print(f"ERROR: publish failed: {e}\n{traceback.format_exc()}")
    finally:
        try:
            if local_video_path and os.path.exists(local_video_path):
                os.remove(local_video_path)
        except Exception:
            pass

    return (f"ok: processed {json_blob_name}", 200)

# --- Upload stubs ---
def _upload_youtube(local_filename: str, title: str, description: str, tags: list[str] | None = None):
    """Uploads a video to YouTube from a local file path."""
    print(f"[stub] Would upload to YouTube: {local_filename}, title={title}")
    # Example:
    # media = MediaFileUpload(local_filename, chunksize=8 * 1024 * 1024, resumable=True)
    # ... build body, insert, next_chunk loop ...
    pass

def _upload_facebook(local_filename: str, title: str, description: str):
    """Uploads a video to Facebook from a local file path."""
    print(f"[stub] Would upload to Facebook: {local_filename}, title={title}")
    # ... actual Facebook upload logic ...
    pass