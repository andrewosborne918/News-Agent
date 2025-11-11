from google.cloud import storage
import tempfile, os

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
def _download_gcs_to_tempfile(bucket_name: str, blob_name: str) -> str:
    """Download gs://bucket/blob to a local temporary file and return its path."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    _, ext = os.path.splitext(blob_name)
    fd, tmp = tempfile.mkstemp(suffix=ext or ".bin")
    os.close(fd)
    blob.download_to_filename(tmp)
    return tmp
"""
Google Cloud Function: Automatically post videos to YouTube Shorts + Facebook
Triggers when a new video is uploaded to Google Cloud Storage

Enhancements:
- Adds _polish_caption_with_ai() to rewrite title/description/hashtags in a
  concise, neutral, professional news voice suitable for narration.
- Normalizes hashtags for YouTube/Facebook.
- Graceful fallback if AI is unavailable or returns bad output.
"""

from pathlib import Path

from google.cloud import storage

import os
import tempfile
import time
import random
import json
from typing import Dict, Any, List, Tuple
import functions_framework
from cloudevents.http import CloudEvent


from google.cloud import storage, secretmanager
from google.api_core.exceptions import NotFound
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError, ResumableUploadError
import requests

# -------- caption_utils fallback shim --------
try:
    from uploader.caption_utils import build_title_and_caption
        _create_post_marker_or_skip,
        _load_json,
        _ensure_caption,
        _build_caption,
        ensure_caption_dict,
    )
    _CAPTION_UTILS_AVAILABLE = True
    print("caption_utils: using bundled implementation")
except Exception as e:
    _CAPTION_UTILS_AVAILABLE = False
    print(f"caption_utils: not found, using local shim ({e})")
    import json
    import os
    from google.cloud import storage

    def _load_json(bucket_name: str, blob_name: str) -> dict:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        data = blob.download_as_bytes()
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return json.loads(data)

    from google.api_core.exceptions import Conflict, PreconditionFailed

    def _create_post_marker_or_skip(bucket_name: str, video_id: str) -> bool:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        marker_key = f"posted/{video_id}.lock"
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

    def _ensure_caption(meta: dict) -> dict:
        title = meta.get("Title") or meta.get("title") or "Update"
        desc = meta.get("Description") or meta.get("description") or ""
        tags = meta.get("Tags") or meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]
        norm = []
        for t in tags:
            t = t.strip("# ").replace(" ", "")
            if not t:
                continue
            norm.append("#" + t[:50])
            if len(norm) >= 25:
                break
        meta["Title"] = str(title)[:95]
        meta["Description"] = str(desc)[:4950]
        meta["Tags"] = norm
        return meta
# ---------- end shim ----------

# Get project ID from environment (auto-injected by Cloud Functions)
PROJECT_ID = os.environ.get("GCP_PROJECT")

# -----------------------------
# Secrets + helpers
# -----------------------------

def _get_secret(name: str) -> str:
    """Retrieve secret from Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()
    path = client.secret_version_path(PROJECT_ID, name, "latest")
    response = client.access_secret_version(request={"name": path})
    return response.payload.data.decode()

def _try_get_secret(name: str):
    """Return secret value or None if it doesn't exist."""
    try:
        return _get_secret(name)
    except NotFound:
        return None

# -----------------------------
# Companion metadata (optional)
# -----------------------------

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
        with open(tmp, "r", encoding="utf-8") as f:
            data = json.load(f)
        os.remove(tmp)
        if isinstance(data, dict):
            print(f"DEBUG: Found companion metadata JSON: {meta_blob_name}")
            print(f"DEBUG:   Title: {data.get('title', 'N/A')}")
            print(f"DEBUG:   Description: {data.get('description', 'N/A')[:100]}.")
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

# -----------------------------
# Storage + uploads
# -----------------------------

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
    
    # Create credentials (support combined secret or individual fields)
    creds_json = _try_get_secret("YOUTUBE_CREDENTIALS_JSON")
    if creds_json:
        data = json.loads(creds_json)
        creds = Credentials(
            token=None,
            refresh_token=data["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
    else:
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
    token = _get_secret("FACEBOOK_PAGE_TOKEN")
    
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

# -----------------------------
# AI Polishing (new)
# -----------------------------

def _normalize_hashtags(raw_tags: List[str], limit: int = 20) -> List[str]:
    """Normalize and de-duplicate hashtags (drop '#', trim, no spaces, a-z0-9 only)."""
    cleaned = []
    seen = set()
    for t in raw_tags or []:
        if not t:
            continue
        t = t.strip()
        # Remove leading '#'
        if t.startswith("#"):
            t = t[1:]
        # Replace spaces/invalid with nothing, lowercase
        t = "".join(ch for ch in t.lower() if ch.isalnum())
        # Skip very short tokens
        if len(t) < 2:
            continue
        if t not in seen:
            cleaned.append(f"#{t}")
            seen.add(t)
        if len(cleaned) >= limit:
            break
    return cleaned

def _polish_caption_with_ai(parts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use Gemini to rewrite the title/description/hashtags into a professional news tone.
    Requires Secret Manager key: GEMINI_API_KEY
    Falls back to original parts if unavailable or on error.
    """
    api_key = _try_get_secret("GEMINI_API_KEY")
    if not api_key:
        print("Polish: GEMINI_API_KEY not found — skipping AI polish.")
        # Still normalize hashtags if present
        parts["hashtags"] = _normalize_hashtags(parts.get("hashtags") or parts.get("tags", []))
        return parts

    # Build input payload for the model
    source_title = (parts.get("title") or "").strip()
    source_desc = (parts.get("description") or "").strip()

    # If caption_utils also produced a long `script`/`narration`, include it
    source_script = (parts.get("script") or parts.get("narration") or "").strip()

    # Compose a single source block with whatever we have
    story_block = "\n\n".join([s for s in [source_title, source_desc, source_script] if s])

    prompt = f"""
You are a newsroom copy editor. Rewrite this into a short, broadcast-ready news package:

- Voice: neutral, concise, confident (anchor-style).
- Style: smooth, natural for spoken narration; no filler; no opinion cues.
- Include: 
  1) a crisp SEO-friendly Title (≤ 90 chars),
  2) a 2–4 sentence Description suitable for YouTube & Facebook (≤ 500 chars),
  3) 8–15 topical Hashtags (single words, no spaces; return as a JSON array).

Return strictly as minified JSON with keys: title, description, hashtags.

SOURCE:
{story_block}
""".strip()

    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        headers = {"Content-Type": "application/json"}
        body = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 512
            }
        }
        r = requests.post(f"{url}?key={api_key}", headers=headers, json=body, timeout=25)
        if not r.ok:
            print(f"Polish: Gemini HTTP {r.status_code} — {r.text[:250]}")
            parts["hashtags"] = _normalize_hashtags(parts.get("hashtags") or parts.get("tags", []))
            return parts

        data = r.json()
        # Extract the text from the first candidate
        text = ""
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            # Some responses use 'output' or other shapes; fallback
            text = json.dumps(data)[:500]

        # The model returns JSON—parse it
        polished = json.loads(text)
        new_title = (polished.get("title") or source_title).strip()[:100]
        new_desc = (polished.get("description") or source_desc).strip()[:4900]
        new_tags = polished.get("hashtags") or []
        if isinstance(new_tags, str):
            # If someone returns comma delimited string
            new_tags = [t.strip() for t in new_tags.split(",")]

        parts["title"] = new_title or parts.get("title")
        parts["description"] = new_desc or parts.get("description")
        parts["hashtags"] = _normalize_hashtags(list(new_tags) or parts.get("hashtags") or parts.get("tags", []))
        return parts

    except Exception as e:
        print(f"Polish: Exception — {e}")
        parts["hashtags"] = _normalize_hashtags(parts.get("hashtags") or parts.get("tags", []))
        return parts

# -----------------------------
# Entry point
# -----------------------------


# -----------------------------
# Core processor (shared by all triggers)
# -----------------------------

def _process_metadata_json(bucket_name: str, json_blob_name: str) -> tuple[str, int]:
    """
    Reads companion JSON, ensures caption present, and kicks off publishing.
    Returns (message, http_status).
    """
    import os
    import traceback

    print("Processor invoked")
    print("============================================================")
    print(f"Bucket: {bucket_name}")
    print(f"JSON:   {json_blob_name}")

    # Idempotency: create .posted marker or skip if it already exists
    if not _create_post_marker_or_skip(bucket_name, json_blob_name):
        return (f"skip: already posted -> {json_blob_name}", 200)

    # Load the JSON metadata
    try:
        meta = _load_json(bucket_name, json_blob_name)
    except Exception as e:
        print(f"ERROR: failed to load metadata JSON: {e}")
        # 200 so Scheduler doesn't retry forever
        return ("failed to load metadata", 200)

    # Ensure Title/Description/Tags exist (normalize to lower-case keys)
    try:
        # If you imported ensure_caption_dict from caption_utils, use it:
        try:
            meta = ensure_caption_dict(meta or {})  # preferred
        except NameError:
            # Fallback: call _ensure_caption directly if wrapper isn't imported
            meta = _ensure_caption(meta or {})
    except Exception as e:
        print(f"ERROR: _ensure_caption failed: {e}")
        # minimal fallback
        meta = meta or {}
        meta = {
            "title": meta.get("title") or meta.get("Title") or "Update",
            "description": (meta.get("description") or meta.get("Description") or "").strip(),
            "hashtags": meta.get("hashtags") or meta.get("Tags") or [],
        }

    # Build title + final caption (caption_utils._build_caption returns ONE string)
    try:
        title = (meta.get("title") or meta.get("Title") or "Update").strip()
        description = (meta.get("description") or meta.get("Description") or "").strip()
        tags = meta.get("hashtags") or meta.get("Tags") or []
    meta = {"title": title, "description": description, "hashtags": tags}
    title, caption = build_title_and_caption(meta)
    logger.info(f"caption type: {type(title).__name__},{type(caption).__name__}")

    # Idempotency marker: processed_markers/{json_blob_name}.done
    storage_client = storage.Client()
    marker_name = f"processed_markers/{json_blob_name}.done"
    bucket = storage_client.bucket(bucket_name)
    marker_blob = bucket.blob(marker_name)
    if marker_blob.exists():
        logger.info("Already processed, skipping.")
        return (f"already processed: {json_blob_name}", 200)
    except Exception as e:
        logger.exception("ERROR: caption build failed: %s", e)
        title = (meta.get("title") or meta.get("Title") or "Update").strip()
        description = (meta.get("description") or meta.get("Description") or "").strip()
        tags = meta.get("hashtags") or meta.get("Tags") or []
        caption = description  # safe fallback

    print(f"  _build_caption type: {type(caption).__name__}, length: {len(caption)}")
    print(f"  Title: {title[:80]}{'...' if len(title) > 80 else ''}")
    print(f"  Description: {caption[:100]}{'...' if len(caption) > 100 else ''}")
    print(f"  Tags: {tags}")


    # Derive companion video path from the JSON name (same prefix, .mp4)
    base_no_ext = os.path.splitext(json_blob_name)[0]
    video_blob_name = base_no_ext + ".mp4"
    print(f"  Video candidate: {video_blob_name}")

    # ---- do the uploads ----
    local_video_path = _download_gcs_to_tempfile(bucket_name, video_blob_name)
    try:
        print(f"Uploading to YouTube: {video_blob_name}")
        _upload_youtube(local_video_path, title, caption, tags)
        print("[youtube] done")

        print(f"Uploading to Facebook: {video_blob_name}")
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

    # On success, upload marker
    try:
        marker_blob.upload_from_string("ok")
    except Exception as e:
        logger.warning(f"Failed to write processed marker: {e}")
    return (f"ok: processed {json_blob_name}", 200)




# -----------------------------
# GCS -> Social entry point (CloudEvent)
# -----------------------------

@functions_framework.cloud_event
def gcs_to_social(event):
    data = event.data or {}
    bucket = data.get("bucket")
    name = data.get("name")
    if not bucket or not name:
        print("No bucket/name in event; ignoring"); return
    if not name.startswith("incoming/"):
        print(f"Ignoring object outside incoming/: {name}"); return
    if not name.lower().endswith(".json"):
        print(f"Ignoring non-json object: {name}"); return
    print("============================================================")
    print("Processor invoked")
    print("============================================================")
    print(f"Bucket: {bucket}")
    print(f"JSON:   {name}")
    body, status = _process_metadata_json(bucket, name)
    print(body)

# -----------------------------
# HTTP triggers for manual + scheduled posting
# -----------------------------

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

def _is_within_posting_window(now_utc=None) -> bool:
    """Return True if current time in America/Detroit is between 06:00 and 21:00 inclusive."""
    import datetime as _dt
    if now_utc is None:
        now_utc = _dt.datetime.now(tz=_dt.timezone.utc)
    tz = ZoneInfo("America/Detroit") if ZoneInfo else None
    local = now_utc.astimezone(tz) if tz else now_utc
    start = local.replace(hour=6, minute=0, second=0, microsecond=0)
    end   = local.replace(hour=21, minute=0, second=0, microsecond=0)
    return start <= local <= end

def manual_post(request):
    """HTTP endpoint to manually post a specific metadata JSON.

    Request body (JSON) or query params:
      - bucket: GCS bucket holding the JSON
      - blob:   path to the metadata JSON (e.g. incoming/news_video_123.json)

    Responds with 200 on success (or 200 if idempotency marker already existed).
    """
    try:
        if request.method == "OPTIONS":
            # CORS preflight
            headers = {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }
            return ("", 204, headers)

        data = {}
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}

        bucket = request.args.get("bucket") if request.args else None
        blob   = request.args.get("blob") if request.args else None
        bucket = data.get("bucket") or bucket
        blob   = data.get("blob") or blob

        if not bucket or not blob:
            return (json.dumps({"error":"missing bucket or blob"}), 400, {"Content-Type":"application/json"})

        body, status = _process_metadata_json(bucket, blob)
        return (body, status)
    except Exception as e:
        return (json.dumps({"status":"error","error":str(e)}), 500, {"Content-Type":"application/json"})

def scheduled_post(request):
    """
    HTTP-triggered function. Scans QUEUE_PREFIX in SCHEDULE_BUCKET for a companion
    .json file, processes the first candidate, and always returns 200 to avoid
    retry storms from Cloud Scheduler.
    """
    import os
    from google.cloud import storage
    import json
    import traceback

    # Log some headers for debugging Scheduler calls
    try:
        hdrs = dict(list(request.headers.items())[:12])
        print("scheduled-post: headers sample:", hdrs)
    except Exception:
        pass

    # Accept JSON or raw bytes (octet-stream)
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}
    if not payload:
        try:
            raw = (request.data or b"").decode("utf-8", errors="ignore").strip()
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}

    max_scan = int(payload.get("max_scan", 5))
    print(f"scheduled-post: payload={payload} max_scan={max_scan}")

    bucket_name = (os.environ.get("SCHEDULE_BUCKET") or "").strip()
    prefix = (os.environ.get("QUEUE_PREFIX") or "incoming/").strip()
    if not bucket_name:
        print("scheduled-post: ERROR missing SCHEDULE_BUCKET env")
        return ("missing SCHEDULE_BUCKET", 200)  # 200 so Scheduler doesn't keep retrying

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)

        # Choose the next item to post: scan prefix for .json companions
        print(f"scheduled-post: scanning gs://{bucket_name}/{prefix} for .json")
        candidates = []
        for b in client.list_blobs(bucket, prefix=prefix):
            if not b.name.endswith(".json"):
                continue
            base_no_ext = os.path.splitext(b.name)[0]
            # Skip already-posted markers
            if storage.Blob(bucket=bucket, name=f"{base_no_ext}.posted").exists():
                continue
            candidates.append(b.name)
            if len(candidates) >= max_scan:
                break

        print(f"scheduled-post: found {len(candidates)} candidate(s)")
        if not candidates:
            return ("no candidates", 200)

        # Process the first candidate (or implement your own selection strategy)
        target = candidates[0]
        body, status = _process_metadata_json(bucket_name, target)
        print(f"scheduled-post: result -> {status} {body}")
        return (body, 200)

    except Exception:
        print("scheduled-post: EXCEPTION")
        print(traceback.format_exc())
        return (f"error logged: exception", 200)

