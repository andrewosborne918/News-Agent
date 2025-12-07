import os
import json
import logging
import re
import urllib.request
from typing import Dict, Any, List, Tuple, Optional

from google.cloud import secretmanager
import google.generativeai as genai

# --- Caching and Helpers ---

logger = logging.getLogger(__name__)
_GEMINI_API_KEY_CACHE: Optional[str] = None


def _get_gemini_api_key() -> Optional[str]:
    """Fetch GEMINI_API_KEY from Secret Manager (cached)."""
    global _GEMINI_API_KEY_CACHE
    if _GEMINI_API_KEY_CACHE is not None:
        return _GEMINI_API_KEY_CACHE

    try:
        project_id = os.environ.get("GCP_PROJECT") or os.environ.get(
            "GOOGLE_CLOUD_PROJECT"
        )
        if not project_id:
            logger.warning("No GCP project id found in env; skipping Gemini key.")
            return None

        client = secretmanager.SecretManagerServiceClient()
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


def _looks_generic(text: str) -> bool:
    """Check if a caption looks like a generic fallback."""
    text_lower = (text or "").lower()
    if not text or "..." in text:
        return True
    if "political commentary on today's biggest story" in text_lower:
        return True
    return False


# --- Groq fallback helpers (no extra dependency; uses stdlib HTTP) ---


def _call_groq_chat(prompt: str) -> Optional[str]:
    """Call Groq's chat completions API and return raw content string."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.warning("[groq] GROQ_API_KEY not set; skipping Groq fallback.")
        return None

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write social copy for short news videos.\n"
                    "Always respond with a single JSON object as described by the user."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_completion_tokens": 512,
    }

    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = resp.read().decode("utf-8")
        parsed = json.loads(payload)
        choices = parsed.get("choices") or []
        if not choices:
            logger.warning("[groq] No choices in response: %s", payload)
            return None

        message = choices[0].get("message", {})
        content = message.get("content")
        if not content:
            logger.warning("[groq] Empty content in response: %s", payload)
            return None

        # Groq's OpenAI-compatible API returns a plain string here
        if isinstance(content, str):
            return content

        # If/when they ever return structured parts, handle that too
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content)

        return str(content)
    except Exception as e:
        logger.warning("[groq] Groq API call failed: %s", e)
        return None


def _summarize_with_groq(
    source_text: str, topic_hint: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Use Groq as a backup to produce {title, description, hashtags}."""
    topic_prompt = f"The story is about: {topic_hint}\n" if topic_hint else ""

    prompt = f"""
Analyze the following news article text and generate a social media post in valid JSON.

ARTICLE:
\"\"\"{source_text}\"\"\"

{topic_prompt}

Return ONLY a JSON object in this exact format:

{{
  "title": "A concise, compelling video title (max 90 characters).",
  "description": "A short, engaging 2–3 sentence summary of the story.",
  "hashtags": ["list", "of", "5", "relevant", "hashtags"]
}}
"""

    raw = _call_groq_chat(prompt)
    if not raw:
        return None

    try:
        json_text = _extract_json(raw)
        data = json.loads(json_text)
        if isinstance(data, dict) and "title" in data:
            logger.info("[groq] Successfully generated AI captions.")
            return data
        logger.warning("[groq] Response was not a valid dict: %s", json_text)
        return None
    except Exception as e:
        logger.exception("[groq] Failed to parse Groq response: %s", e)
        return None


# --- AI Caption Generation (Gemini first, then Groq) ---


def summarize_with_gemini(
    source_text: str, topic_hint: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Use Gemini to generate a {title, description, hashtags} dict.
    If Gemini is unavailable or fails, fall back to Groq.
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        logger.warning("[gemini] No API key; trying Groq fallback.")
        return _summarize_with_groq(source_text, topic_hint)

    try:
        genai.configure(api_key=api_key)
        # Keep the model name exactly as you already had it
        model = genai.GenerativeModel("models/gemini-1.5-flash")
    except Exception as e:
        logger.error("[gemini] Failed to configure model: %s", e)
        logger.info("[caption] Falling back to Groq.")
        return _summarize_with_groq(source_text, topic_hint)

    topic_prompt = f"The story is about: {topic_hint}\n" if topic_hint else ""

    prompt = f"""
Analyze the following news article text and generate a social media post in valid JSON format.

ARTICLE:
\"\"\"{source_text}\"\"\"

{topic_prompt}

JSON FORMAT:
{{
  "title": "A concise, compelling video title (max 90 chars).",
  "description": "A short, engaging paragraph (2-3 sentences) summarizing the story.",
  "hashtags": ["list", "of", "5", "relevant", "hashtags"]
}}
"""

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 450,
            },
        )

        raw_text = getattr(response, "text", None) or ""
        json_text = _extract_json(raw_text)
        ai_data = json.loads(json_text)

        if isinstance(ai_data, dict) and "title" in ai_data:
            logger.info("[gemini] Successfully generated AI captions.")
            return ai_data

        logger.warning("[gemini] AI response was not a valid dict: %s", json_text)
    except Exception as e:
        logger.exception("[gemini] Failed to generate content: %s", e)

    # If we got here, Gemini failed or gave junk → try Groq
    logger.info("[caption] Gemini failed; falling back to Groq.")
    return _summarize_with_groq(source_text, topic_hint)


# --- Hashtag utilities ---


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
        tag = "#" + core.lower()
        if tag in seen:
            continue
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


# --- Main Public Function ---


def get_title_description_tags(meta: Dict[str, Any]) -> Tuple[str, str, List[str]]:
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
                title = (ai_data.get("title") or title).strip()
                description = (ai_data.get("description") or description).strip()
                hashtags_list = _coerce_hashtag_list(
                    ai_data.get("hashtags") or hashtags_list
                )
        else:
            logger.warning("[caption] No source text found for AI generation.")

    # Final cleanup and normalization
    if not title:
        title = "Update"

    hashtags = _normalize_hashtags(hashtags_list)
    return title, description, hashtags
