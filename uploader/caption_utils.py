# caption_utils.py
import json
import os
import logging
import re
from typing import Dict, Any, List, Tuple, Optional

from google.cloud import secretmanager
import google.generativeai as genai

# --- Caching and Helpers ---

_GEMINI_API_KEY_CACHE: Optional[str] = None
logger = logging.getLogger(__name__)

def _get_gemini_api_key() -> Optional[str]:
    """Fetch GEMINI_API_KEY from Secret Manager (cached). Returns None if unavailable."""
    global _GEMINI_API_KEY_CACHE
    if _GEMINI_API_KEY_CACHE is not None:
        return _GEMINI_API_KEY_CACHE

    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            logger.warning("No GCP project id found in env; skipping Gemini key.")
            return None

        name = f"projects/{project_id}/secrets/GEMINI_API_KEY/versions/latest"
        response = client.access_secret_version(request={"name": name})
        api_key = response.payload.data.decode("utf-8").strip()
        if not api_key:
            logger.warning("GEMINI_API_KEY secret is empty.")
            return None
        _GEMINI_API_KEY_CACHE = api_key
        return api_key
    except Exception as e:
        logger.warning("Could not load GEMINI_API_KEY from Secret Manager: %s", e)
        return None

def _extract_json(text: str) -> str:
    """Extract the first {...} block from the model output."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else text

def _normalize_hashtags(hashtags: List[str]) -> List[str]:
    """Normalize and deduplicate hashtags."""
    seen = set()
    out: List[str] = []
    for h in hashtags or []:
        h = (h or "").strip()
        if not h:
            continue
        core = h.lstrip("#").replace(" ", "")
        if not core:
            continue
        tag = f"#{core}"
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out

def _coerce_hashtag_list(value: Any) -> List[str]:
    """Accept list or comma/space-separated string; return list[str]."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    
    s = str(value)
    parts = [p.strip() for p in s.replace(",", " ").split() if p.strip()]
    return parts

def _looks_generic(text: str) -> bool:
    """Check if a caption looks like a generic fallback."""
    text_lower = (text or "").lower()
    if not text or "..." in text:
        return True
    if "political commentary on today's biggest story" in text_lower:
        return True
    return False

# --- AI Caption Generation ---

def summarize_with_gemini(
    source_text: str, topic_hint: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Use Gemini to generate a {title, description, hashtags} dict.
    Returns None on failure.
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        logger.warning("[gemini] No API key, cannot summarize.")
        return None
    
    try:
        genai.configure(api_key=api_key)
        # Ensure you are using a valid, available model name
        model = genai.GenerativeModel("models/gemini-1.5-flash")
    except Exception as e:
        logger.error(f"[gemini] Failed to configure model: {e}")
        return None

    topic_prompt = f"The story is about: {topic_hint}\n" if topic_hint else ""
    
    prompt = f"""
    Analyze the following news article text and generate a social media post in valid JSON format.
    
    ARTICLE:
    "{source_text}"
    
    {topic_prompt}
    
    JSON FORMAT:
    {{
      "title": "A concise, compelling video title (max 90 chars).",
      "description": "A short, engaging paragraph (2-3 sentences) summarizing the story.",
      "hashtags": ["list", "of", "5", "relevant", "hashtags"]
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        json_text = _extract_json(response.text)
        ai_data = json.loads(json_text)
        
        if isinstance(ai_data, dict) and "title" in ai_data:
            logger.info("[gemini] Successfully generated AI captions.")
            return ai_data
        else:
            logger.warning(f"[gemini] AI response was not a valid dict: {json_text}")
            return None
    except Exception as e:
        logger.exception(f"[gemini] Failed to generate content: {e}")
        return None

# --- Main Public Function ---

def get_title_description_tags(meta: Dict) -> Tuple[str, str, List[str]]:
    """
    Produce (title, description, hashtags_list) using meta + AI when helpful.
    This is the main function for main.py to call.
    """
    title = (meta.get("title") or meta.get("Title") or "").strip()
    description = (meta.get("description") or meta.get("Description") or "").strip()
    hashtags_raw = meta.get("hashtags") or meta.get("tags") or []
    hashtags_list = _coerce_hashtag_list(hashtags_raw)

    # Check if the captions from meta are generic/bad
    needs_ai = _looks_generic(title) or _looks_generic(description) or not hashtags_list

    if needs_ai:
        logger.warning("[caption] Meta captions look generic. Attempting AI generation.")
        # Pick a source text for AI
        source = (
            meta.get("transcript")
            or meta.get("summary")
            or meta.get("text")
            or description
            or title
            or ""
        )
        source = str(source).strip()

        if source:
            ai_data = summarize_with_gemini(source, topic_hint=title)
            if ai_data:
                # Use AI data, falling back to meta data if a key is missing
                title = (ai_data.get("title") or title).strip()
                description = (ai_data.get("description") or description).strip()
                hashtags_list = _coerce_hashtag_list(ai_data.get("hashtags") or hashtags_list)
        else:
            logger.warning("[caption] No source text found for AI generation.")

    # Final cleanup and normalization
    if not title:
        title = "News Update" # Final fallback title
    
    if not description and title != "News Update":
        description = title 
    
    if not hashtags_list:
        hashtags_list = ["News", "Politics", "BreakingNews"] # Final fallback tags

    final_tags = _normalize_hashtags(hashtags_list)
    
    # Truncate for platform limits
    final_title = title[:100] # YouTube limit
    final_description = description[:5000] # YouTube limit

    return final_title, final_description, final_tags