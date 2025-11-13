# caption_utils.py
import json
import os
import logging
import re
from typing import Dict, Any, List, Tuple, Optional
_GEMINI_API_KEY_CACHE: Optional[str] = None

from google.cloud import secretmanager
import google.generativeai as genai

# Gemini API key cache
_GEMINI_API_KEY_CACHE: str | None = None

def _get_gemini_api_key() -> Optional[str]:
    """Fetch GEMINI_API_KEY from Secret Manager (cached). Returns None if unavailable."""
    global _GEMINI_API_KEY_CACHE
    if _GEMINI_API_KEY_CACHE is not None:
        return _GEMINI_API_KEY_CACHE

    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            logging.warning("No GCP project id found in env; skipping Gemini key.")
            return None

        name = f"projects/{project_id}/secrets/GEMINI_API_KEY/versions/latest"
        response = client.access_secret_version(request={"name": name})
        api_key = response.payload.data.decode("utf-8").strip()
        if not api_key:
            logging.warning("GEMINI_API_KEY secret is empty.")
            return None
        _GEMINI_API_KEY_CACHE = api_key
        return api_key
    except Exception as e:
        logging.warning("Could not load GEMINI_API_KEY from Secret Manager: %s", e)
        return None

def _extract_json(text: str) -> str:
    """Extract the first {...} block from the model output."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else text

def summarize_with_gemini(
    source_text: str, topic_hint: Optional[str] = None
) -> Optional[Tuple[str, str, List[str]]]:
    """
    Use Gemini to generate a (title, description, hashtags) triple from the video source text.
    Returns None on failure so caller can fall back.
    """
    api_key = _get_gemini_api_key()


        title = cleaned_title[:100]
        description = (
            f"{title}\n\n"
            "Stay informed with our daily news shorts.\n\n"
            "#news #shorts #politics #dailynews"
        )

        if not tags:
            tags = ["#news", "#shorts", "#politics", "#dailynews"]

        return title, description, tags
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
