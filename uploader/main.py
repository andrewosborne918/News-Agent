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

from google.cloud import storage, secretmanager
from google.api_core.exceptions import NotFound
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError, ResumableUploadError
import requests

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
        data = json.loads(Path(tmp).read_text(encoding="utf-8"))
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

def _process_metadata_json(bucket: str, blob_name: str) -> tuple[str, int]:
    """
    Shared logic that reads a metadata JSON in GCS and posts the corresponding video
    to the configured platforms. Returns (body, http_status).
    """
    print("="*60)
    print("Processor invoked")
    print("="*60)
    print(f"Bucket: {bucket}")
    print(f"JSON:   {blob_name}")

    if not blob_name.endswith(".json"):
        print(f"Ignoring non-json object: {blob_name}")
        return "", 204

    import os as _os
    video_id = _os.path.splitext(_os.path.basename(blob_name))[0]

    # Idempotency: create posted/{video_id}.lock marker
    from caption_utils import _create_post_marker_or_skip, _load_json, _ensure_caption, _build_caption
    marker_created = _create_post_marker_or_skip(bucket, video_id)
    if not marker_created:
        print(f"[idempotency] marker exists for {video_id}; skipping post")
        return "", 200

    try:
        # Load metadata JSON
        meta = _load_json(bucket, blob_name)

        # Ensure caption parts (title/description/tags/script)
        parts = _ensure_caption(meta)

        # Normalize hashtags and try AI polish
        parts = _build_caption(parts)  # derive title/description/hashtags from script if missing
        parts = _polish_caption_with_ai(parts)

        # Download video from where the JSON points to
        video_bucket = meta.get("video_bucket") or bucket
        video_blob   = meta.get("video_blob") or meta.get("video_path")
        if not video_blob:
            # Fallback: assume same dir/name with .mp4
            import os as _os
            base = _os.path.splitext(blob_name)[0] + ".mp4"
            video_blob = base

        local_path = _download_from_gcs(video_bucket, video_blob)

        # Upload destinations
        upload_to = meta.get("destinations") or ["youtube", "facebook"]

        # YouTube
        if "youtube" in upload_to:
            try:
                yt_result = _upload_youtube(
                    filepath=local_path,
                    title=parts["title"],
                    description=parts["description"],
                    tags=parts.get("hashtags") or parts.get("tags") or []
                )
                print(f"✅ Uploaded to YouTube: {yt_result}")
            except Exception as yt_err:
                print(f"❌ YouTube upload failed: {yt_err}")

        # Facebook
        if "facebook" in upload_to:
            fb_page_id = _try_get_secret("FB_PAGE_ID")
            fb_page_token = _try_get_secret("FB_PAGE_TOKEN")
            if fb_page_id and fb_page_token:
                try:
                    fb_result = _upload_facebook(
                        filepath=local_path,
                        title=parts["title"],
                        description=parts["description"]
                    )
                    print(f"✅ Uploaded to Facebook: {fb_result}")
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
        import os as _os
        try:
            _os.remove(local_path)
        except Exception:
            pass

        # Log posting status
        marker_status = "created" if marker_created else "exists"
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
def gcs_to_social(event, context):
    """GCS trigger: when a companion JSON is uploaded."""
    bucket = event.get("bucket")
    blob_name = event.get("name")
    return _process_metadata_json(bucket, blob_name)



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
    """HTTP endpoint meant to be triggered hourly by Cloud Scheduler.

    Env:
      - SCHEDULE_BUCKET: bucket to scan (required if not provided in request)
      - QUEUE_PREFIX:    prefix to scan for JSONs (default 'incoming/')
    Optional query/body:
      - bucket, prefix: override envs
      - max_scan: how many JSONs to try this tick (default 5)

    Logic:
      - If current time in America/Detroit is outside 06:00–21:00, exit 204.
      - List JSON files by updated time ascending under prefix.
      - Attempt to process up to max_scan until one actually posts (idempotency makes others skip).
    """
    # Time window check
    if not _is_within_posting_window():
        return ("Outside posting window; skipping.", 204)

    data = request.get_json(silent=True) or {}
    bucket = data.get("bucket") or (request.args.get("bucket") if request.args else None) or os.environ.get("SCHEDULE_BUCKET")
    prefix = data.get("prefix") or (request.args.get("prefix") if request.args else None) or os.environ.get("QUEUE_PREFIX", "incoming/")
    max_scan = int(data.get("max_scan") or (request.args.get("max_scan") if request.args else "5"))

    if not bucket:
        return (json.dumps({"error":"missing bucket (set SCHEDULE_BUCKET env or pass ?bucket=)"}), 400, {"Content-Type":"application/json"})

    client = storage.Client()
    bucket_obj = client.bucket(bucket)

    # Collect candidate JSONs
    blobs = list(client.list_blobs(bucket, prefix=prefix))
    candidates = [b for b in blobs if b.name.endswith(".json")]
    # Sort by updated time asc (older first)
    try:
        candidates.sort(key=lambda b: b.updated or b.time_created)
    except Exception:
        pass

    tried = 0
    for b in candidates:
        tried += 1
        body, status = _process_metadata_json(bucket, b.name)
        # If status 200, we consider it handled (even if idempotent skip). Move on.
        if status == 200:
            return (body, 200)
        if tried >= max_scan:
            break

    return ("No candidates processed.", 204)
