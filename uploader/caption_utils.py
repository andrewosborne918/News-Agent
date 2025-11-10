import os
import json
from google.cloud import storage
from google.api_core.exceptions import Conflict

# Try to import AI caption generator
try:
    from generate_caption import generate_caption_with_ai
except ImportError:
    generate_caption_with_ai = None

def _load_json(bucket_name: str, name: str) -> dict:
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(name)
    return json.loads(blob.download_as_text())

def _looks_generic(text: str) -> bool:
    if not text:
        return True
    t = text.strip().lower()
    generic_starts = [
        "the u.s.", "political commentary", "today's top story",
        "watch to get the full analysis"
    ]
    return any(t.startswith(gs) for gs in generic_starts)

def _ensure_caption(meta: dict) -> dict:
    """
    Ensures meta has good 'title', 'description', 'hashtags' (list[str]).
    Uses transcript/summary in meta as source text. Falls back gracefully.
    """
    title = (meta.get("title") or "").strip()
    description = (meta.get("description") or "").strip()
    hashtags = meta.get("hashtags") or []

    source = (meta.get("transcript") or meta.get("summary") or meta.get("text") or "").strip()

    needs_ai = _looks_generic(title) or _looks_generic(description) or not hashtags

    if needs_ai:
        if generate_caption_with_ai:
            # Use AI to generate all three
            ai = generate_caption_with_ai([source], os.getenv("GEMINI_API_KEY")) if source else None
            if ai:
                title = ai.get("title", title) or title
                description = ai.get("description", description) or description
                hashtags = ai.get("hashtags", hashtags) or hashtags
        else:
            # Minimal built-in fallback
            if not title and source:
                title = source.split(".")[0][:100]
            if not description and source:
                description = source[:260]
            if not hashtags:
                hashtags = ["RightSideReport", "Politics"]

    # Normalize hashtags to '#Tag' format
    tags = []
    for h in hashtags:
        h = h.strip()
        if not h:
            continue
        if not h.startswith("#"):
            h = "#" + h.replace(" ", "")
        tags.append(h)

    return {"title": title, "description": description, "hashtags": tags}

def _build_caption(parts: dict) -> str:
    title = parts["title"].strip()
    desc = parts["description"].strip()
    tags = " ".join(parts["hashtags"])
    return f"{title}\n\n{desc}\n\n{tags}".strip()

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
    except Conflict:
        print(f"[idempotency] marker exists {marker_key}; skipping")
        return False
