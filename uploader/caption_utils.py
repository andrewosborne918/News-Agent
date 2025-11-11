# caption_utils.py
import json
import os
from typing import Dict, List
from google.cloud import storage
from google.api_core.exceptions import Conflict

# ---------------------------------------------------------------------------
# Gemini setup (prefers new google-genai SDK, falls back to google-generativeai)
# ---------------------------------------------------------------------------

_GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")  # or "gemini-flash-latest"
_client = None
_use_new_sdk = False
_legacy_model = None

try:
    # ✅ Preferred modern SDK (google-genai)
    from google import genai  # pip install google-genai
    _client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    _use_new_sdk = True
    print("[Gemini] Using new google-genai SDK with model", _GEMINI_MODEL_NAME)
except Exception:
    try:
        # 🧩 Fallback to legacy SDK (google-generativeai)
        import google.generativeai as generativeai  # pip install google-generativeai
        if os.environ.get("GEMINI_API_KEY"):
            generativeai.configure(api_key=os.environ["GEMINI_API_KEY"])
            _legacy_model = generativeai.GenerativeModel(_GEMINI_MODEL_NAME)
            print("[Gemini] Using legacy google-generativeai SDK with model", _GEMINI_MODEL_NAME)
    except Exception as e:
        print(f"[Gemini] No valid SDK available: {e}")

# ---------------------------------------------------------------------------
# Gemini helper
# ---------------------------------------------------------------------------

def _rewrite_caption(text: str, limit: int = 150) -> str:
    """Use Gemini to rewrite a caption; returns original text on any failure."""
    if not text:
        return text
    try:
        prompt = (
            "Rewrite the following social caption in a neutral, professional tone. "
            f"Keep it under {limit} characters. Return only the rewritten text.\n\n{text}"
        )
        if _use_new_sdk and _client:
            resp = _client.models.generate_content(model=_GEMINI_MODEL_NAME, contents=prompt)
            return (resp.text or "").strip() or text
        elif _legacy_model:
            resp = _legacy_model.generate_content(prompt)
            return (getattr(resp, "text", "") or "").strip() or text
    except Exception as e:
        print(f"[WARN] Gemini rewrite failed: {e}")
    return text

# ---------------------------------------------------------------------------
# Optional import for your existing AI caption generator (if present)
# ---------------------------------------------------------------------------

try:
    from generate_caption import generate_caption_with_ai  # type: ignore
except Exception:
    generate_caption_with_ai = None

# ---------------------------------------------------------------------------
# GCS utilities
# ---------------------------------------------------------------------------

def _load_json(bucket_name: str, name: str) -> Dict:
    """Load a JSON blob from GCS."""
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(name)
    return json.loads(blob.download_as_text())

# ---------------------------------------------------------------------------
# Caption helpers
# ---------------------------------------------------------------------------

def _looks_generic(text: str) -> bool:
    if not text:
        return True
    t = text.strip().lower()
    generic_starts = [
        "the u.s.",
        "political commentary",
        "today's top story",
        "watch to get the full analysis",
    ]
    return any(t.startswith(gs) for gs in generic_starts)

def _normalize_hashtags(hashtags: List[str]) -> List[str]:
    """Normalize and deduplicate hashtags."""
    seen = set()
    out: List[str] = []
    for h in hashtags or []:
        h = (h or "").strip()
        if not h:
            continue
        if not h.startswith("#"):
            h = "#" + h.replace(" ", "")
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out

# ---------------------------------------------------------------------------
# Core caption ensuring logic
# ---------------------------------------------------------------------------

def _ensure_caption(meta: Dict) -> Dict:
    """
    Ensures meta has 'title', 'description', and 'hashtags'.
    Uses transcript/summary/text as fallback and optionally calls Gemini.
    """
    title = (meta.get("title") or "").strip()
    description = (meta.get("description") or "").strip()
    hashtags = meta.get("hashtags") or []

    source = (meta.get("transcript") or meta.get("summary") or meta.get("text") or "").strip()
    needs_ai = _looks_generic(title) or _looks_generic(description) or not hashtags

    if needs_ai:
        if generate_caption_with_ai and source:
            try:
                ai = generate_caption_with_ai([source], os.getenv("GEMINI_API_KEY"))
            except Exception as e:
                print(f"[WARN] generate_caption_with_ai failed: {e}")
                ai = None
            if ai:
                title = (ai.get("title") or title or "").strip()
                description = (ai.get("description") or description or "").strip()
                hashtags = ai.get("hashtags") or hashtags or []
        else:
            # Use Gemini rewrite for minimal polishing
            if title:
                title = _rewrite_caption(title, limit=100)
            elif source:
                title = _rewrite_caption(source.split(".")[0][:100], limit=100)

            if description:
                description = _rewrite_caption(description, limit=260)
            elif source:
                description = _rewrite_caption(source[:260], limit=260)

            if not hashtags:
                hashtags = ["RightSideReport", "Politics"]

    tags = _normalize_hashtags(hashtags)
    return {"title": title, "description": description, "hashtags": tags}

# ---------------------------------------------------------------------------
# Caption building and idempotency utilities
# ---------------------------------------------------------------------------

def _build_caption(parts: Dict) -> str:
    """Build a final caption string."""
    title = (parts.get("title") or "").strip()
    desc = (parts.get("description") or "").strip()
    tags = " ".join(parts.get("hashtags") or [])
    body = "\n\n".join(x for x in [title, desc, tags] if x).strip()
    return body

def _create_post_marker_or_skip(bucket_name: str, video_id: str) -> bool:
    """Create an idempotency marker in GCS to prevent duplicate posting."""
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

# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def ensure_and_build_caption(meta: Dict) -> str:
    """Return a final caption string after ensuring and cleaning fields."""
    return _build_caption(_ensure_caption(meta))

def ensure_caption_dict(meta: Dict) -> Dict:
    """Return the normalized caption dictionary."""
    return _ensure_caption(meta)
