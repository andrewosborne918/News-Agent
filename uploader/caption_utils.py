# caption_utils.py
import json
import os
from typing import Dict, List, Tuple, Optional

# Optional: only used if you call _load_json()
try:
    from google.cloud import storage
except Exception:
    storage = None  # keeps module import-safe on local runs

from google.api_core.exceptions import Conflict, PreconditionFailed  # noqa: F401 (kept for parity)

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
            return (getattr(resp, "text", "") or "").strip() or text
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
    generate_caption_with_ai = None  # type: ignore

# ---------------------------------------------------------------------------
# (Optional) GCS utilities
# ---------------------------------------------------------------------------

def _load_json(bucket_name: str, name: str) -> Dict:
    """Load a JSON blob from GCS."""
    if storage is None:
        raise RuntimeError("google-cloud-storage not available in this environment")
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
    """Normalize and deduplicate hashtags to #CamelCaseNoSpaces style."""
    seen = set()
    out: List[str] = []
    for h in hashtags or []:
        h = (h or "").strip()
        if not h:
            continue
        # Strip leading '#', remove spaces, keep alnum/underscore mostly intact
        core = h.lstrip("#").replace(" ", "")
        if not core:
            continue
        tag = f"#{core}"
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out

def _coerce_hashtag_list(value) -> List[str]:
    """Accept list or comma/space-separated string; return list[str]."""
    if value is None:
        return []
    if isinstance(value, list):
        # flatten simple scalar-like entries
        return [str(v).strip() for v in value if str(v).strip()]
    # treat as string
    s = str(value)
    # allow commas or whitespace as separators
    parts = [p.strip() for p in s.replace(",", " ").split() if p.strip()]
    return parts

# ---------------------------------------------------------------------------
# Core derivation pipeline (single source of truth)
# ---------------------------------------------------------------------------

def _derive_title_desc_tags(meta: Dict) -> Tuple[str, str, List[str]]:
    """
    Produce (title, description, hashtags_list) using meta + AI when helpful.
    Never returns None; always returns strings and list.
    """
    title = (meta.get("title") or meta.get("Title") or "").strip()
    description = (meta.get("description") or meta.get("Description") or "").strip()
    hashtags_raw = meta.get("hashtags") or meta.get("tags") or []
    hashtags_list = _coerce_hashtag_list(hashtags_raw)

    # Pick a source text for AI: transcript > summary > text > description > title
    source = (
        meta.get("transcript")
        or meta.get("summary")
        or meta.get("text")
        or description
        or title
        or ""
    )
    source = str(source).strip()

    needs_ai = _looks_generic(title) or _looks_generic(description) or not hashtags_list

    if needs_ai:
        # Prefer user's AI generator if present
        if generate_caption_with_ai and source:
            try:
                ai = generate_caption_with_ai([source], os.getenv("GEMINI_API_KEY"))
            except Exception as e:
                print(f"[WARN] generate_caption_with_ai failed: {e}")
                ai = None
            if ai:
                title = (ai.get("title") or title or "").strip()
                description = (ai.get("description") or description or "").strip()
                hashtags_list = _coerce_hashtag_list(ai.get("hashtags") or hashtags_list)
        else:
            # Minimal Gemini polish for existing text, or synthesize from source
            if title:
                title = _rewrite_caption(title, limit=100)
            elif source:
                title = _rewrite_caption(source.split(".")[0][:100], limit=100)  # first sentence-ish

            if description:
                description = _rewrite_caption(description, limit=260)
            elif source:
                description = _rewrite_caption(source[:260], limit=260)

            if not hashtags_list:
                hashtags_list = ["RightSideReport", "Politics"]

    hashtags = _normalize_hashtags(hashtags_list)
    if not title:
        title = "Update"
    return title, description, hashtags

def _compose_caption_text(title: str, description: str, hashtags: List[str]) -> str:
    """Join pieces into a final social caption text."""
    parts: List[str] = []
    if title:
        parts.append(title)
    if description:
        parts.append(description)
    if hashtags:
        parts.append(" ".join(hashtags))
    return "\n\n".join(parts).strip()

# ---------------------------------------------------------------------------
# Public APIs (use these from other modules)
# ---------------------------------------------------------------------------

def build_title_and_caption(meta: Dict) -> Tuple[str, str]:
    """
    Canonical function for callers.
    Always returns exactly (title, caption).
    """
    print("[caption] build_title_and_caption invoked")
    print("[caption] build_title_and_caption invoked")
    title, description, hashtags = _derive_title_desc_tags(meta)
    caption = _compose_caption_text(title, description, hashtags)
    return title, caption

def ensure_caption_dict(meta: Dict) -> Dict:
    """
    Return normalized caption fields:
        {
          "title": str,
          "description": str,
          "hashtags": List[str]
        }
    """
    title, description, hashtags = _derive_title_desc_tags(meta)
    return {"title": title, "description": description, "hashtags": hashtags}

def ensure_and_build_caption(meta: Dict) -> str:
    """
    Legacy convenience: returns final caption text.
    Prefer build_title_and_caption() in new code.
    """
    title, description, hashtags = _derive_title_desc_tags(meta)
    return _compose_caption_text(title, description, hashtags)
