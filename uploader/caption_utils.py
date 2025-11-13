# caption_utils.py
import json
import os
import logging
import re
from typing import Dict, Any, List, Tuple

from google.cloud import secretmanager
import google.generativeai as genai

# Gemini API key cache
_GEMINI_API_KEY_CACHE: str | None = None

def _get_gemini_api_key() -> str | None:
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

def summarize_with_gemini(source_text: str, topic_hint: str | None = None) -> Tuple[str, str, List[str]] | None:
    """
    Use Gemini to generate a (title, description, hashtags) triple from the video source text.
    Returns None on failure so caller can fall back.
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        logging.info("No GEMINI_API_KEY available; skipping AI caption.")
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt_parts = [
            "You are writing social copy for a short conservative news video.",
            "Write a compelling but factual YouTube Shorts title, description, and hashtags.",
            "Tone: neutral, concise, professional news voice. Do NOT editorialize or speculate.",
            "Assume the viewer has not seen the video yet.",
            "",
            "Return ONLY a JSON object with this exact shape:",
            '{',
            '  "title": "short headline (max 90 chars)",',
            '  "description": "2-4 sentences summarizing the story, plus 1-2 short lines for context",',
            '  "hashtags": ["tag1","tag2","tag3"]  // 5-15 tags, no # symbols, lowercase words',
            '}',
            "",
            "Constraints:",
            "- Stay strictly within what is explicitly stated in the source text.",
            "- No predictions, no opinions, no loaded language.",
            "- Use U.S. political context where relevant.",
        ]

        if topic_hint:
            prompt_parts.append(f"\nTopic hint: {topic_hint}")

        prompt_parts.append("\nSource content for the video:\n")
        prompt_parts.append(source_text[:12000])  # keep under token limits

        prompt = "\n".join(prompt_parts)

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 512,
            },
        )

        if hasattr(response, "text") and response.text:
            raw = response.text
        else:
            parts_text: List[str] = []
            for cand in getattr(response, "candidates", []):
                for part in getattr(cand.content, "parts", []):
                    if getattr(part, "text", None):
                        parts_text.append(part.text)
            raw = "\n".join(parts_text)

        raw = raw.strip()
        if not raw:
            logging.warning("Gemini returned empty caption response.")
            return None

        json_str = _extract_json(raw)
        data = json.loads(json_str)

        title = str(data.get("title", "")).strip()[:100] or "Daily News Update"
        description = str(data.get("description", "")).strip() or title
        hashtags = data.get("hashtags") or []

        tags: List[str] = []
        seen = set()
        for tag in hashtags:
            if not isinstance(tag, str):
                continue
            cleaned = re.sub(r"[^a-zA-Z0-9_]", "", tag.lower())
            if not cleaned:
                continue
            tag_with_hash = "#" + cleaned
            if tag_with_hash not in seen:
                seen.add(tag_with_hash)
                tags.append(tag_with_hash)
        tags = tags[:15]

        return title, description, tags

    except Exception as e:
        logging.warning("Gemini caption generation failed: %s", e)
        return None

def get_title_description_tags(meta: Dict[str, Any]) -> Tuple[str, str, List[str]]:
    """
    Decide title/description/tags for the upload.

    Priority:
    1) If Gemini can summarize from qa_text / video_script → use that.
    2) Else, if companion JSON provides title/description/hashtags → use those.
    3) Else, fall back to your existing heuristic logic.
    """
    source_text = None

    if isinstance(meta.get("qa_text"), str) and meta["qa_text"].strip():
        source_text = meta["qa_text"].strip()
    elif isinstance(meta.get("video_script"), str) and meta["video_script"].strip():
        source_text = meta["video_script"].strip()

    topic_hint = (meta.get("title") or meta.get("topic") or "").strip() or None

    if source_text:
        ai_result = summarize_with_gemini(source_text, topic_hint=topic_hint)
        if ai_result is not None:
            return ai_result

    meta_title = (meta.get("title") or "").strip()
    meta_desc = (meta.get("description") or "").strip()
    raw_tags = meta.get("hashtags") or []

    if not isinstance(raw_tags, list):
        raw_tags = [raw_tags]

    tags: List[str] = []
    for t in raw_tags:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t.lstrip("#")
        tags.append(t)
    tags = tags[:15]

    if meta_title and meta_desc:
        return meta_title[:100], meta_desc[:4900], tags

    cleaned_title = (meta.get("original_filename") or "Daily News Update").replace("_", " ").title()
    title = cleaned_title[:100]
    description = (
        f"{title}\n\nStay informed with our daily news shorts.\n\n"
        "#news #shorts #politics #dailynews"
    )
    if not tags:
        tags = ["#news", "#shorts", "#politics", "#dailynews"]

    return title, description, tags
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
