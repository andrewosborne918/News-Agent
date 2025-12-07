# caption_utils.py
import json
import os
import logging
import re
import time
from typing import Dict, Any, List, Tuple, Optional

import gspread
from google.cloud import secretmanager
import google.generativeai as genai
import google.auth
from google.api_core.exceptions import ResourceExhausted, InternalServerError
from groq import Groq


def generate_with_model_fallback(prompt: str, model_list: List[str]):
    """
    Tries to generate content with a list of Gemini models, falling back on quota errors.
    """
    if not model_list:
        raise ValueError("Model list cannot be empty.")
    
    last_error: Optional[Exception] = None
    
    for i, model_name in enumerate(model_list):
        is_last_model = (i == len(model_list) - 1)
        
        try:
            print(f"ℹ️  Attempting generation with: {model_name}")
            model = genai.GenerativeModel(model_name)
            return model.generate_content(prompt)
        
        except ResourceExhausted as e:
            # 429 Quota Error. Try the next model.
            print(f"⚠️  Quota limit on {model_name}. Trying next model...")
            last_error = e
            if is_last_model:
                print("❌ All fallback models are also rate-limited. Raising error.")
                raise e
            continue  # Try next model
        
        except InternalServerError as e:
            # 500 Server Error. Pause, retry *this* model once.
            print(f"⚠️  Server error on {model_name}. Pausing for 10s and retrying...")
            last_error = e
            time.sleep(10)
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt)
            except Exception as retry_e:
                print(f"❌ Retry failed for {model_name}. Trying next model...")
                last_error = retry_e
                if is_last_model:
                    raise retry_e
                continue  # Try next model
                
        except Exception as e:
            # Other error (Safety, etc.). Try the next model immediately.
            print(f"❌ Non-quota error on {model_name}: {e}. Trying next model...")
            last_error = e
            if is_last_model:
                print("❌ All fallback models also failed. Raising error.")
                raise e
            continue  # Try next model
    
    # This should not be reachable, but as a safeguard
    if last_error:
        raise last_error
    else:
        raise Exception("Failed to generate content after trying all models.")


# --- Caching and Helpers ---
_GEMINI_API_KEY_CACHE: Optional[str] = None
_GROQ_CLIENT_CACHE: Optional[Groq] = None
logger = logging.getLogger(__name__)

# --- Google Sheet Configuration ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/11lXogVfFS-VZWuVImTAfiZTDRc4v1LAmoTu9JR9y03U/edit"
SHEET_TAB_NAME = "AnswerSegment"
SHEET_KEY_COLUMN = 1  # Column A (run_id)
SHEET_DATA_COLUMN = 4  # Column D (sentence_text)
_SHEET_CLIENT_CACHE: Optional[gspread.Spreadsheet] = None
# ----------------------------------------


def _get_sheet_client() -> Optional[gspread.Spreadsheet]:
    """Connects to the Google Sheet using default environment creds."""
    global _SHEET_CLIENT_CACHE
    if _SHEET_CLIENT_CACHE:
        return _SHEET_CLIENT_CACHE

    try:
        # Explicitly use the default compute credentials
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ]
        creds, _ = google.auth.default(scopes=scopes)
        gc = gspread.authorize(creds)

        sh = gc.open_by_url(SHEET_URL)
        _SHEET_CLIENT_CACHE = sh
        logger.info("[sheets] Successfully connected to Google Sheet.")
        return sh
    except Exception as e:
        # Log the full error, including if it's a permissions issue
        logger.error("[sheets] Failed to connect to Google Sheet: %s", e, exc_info=True)
        return None


def _get_answers_from_sheet(run_id_key: str) -> Optional[str]:
    """
    Fetches all 'sentence_text' values for a given 'run_id'
    and concatenates them into a single string.
    """
    if not run_id_key:
        return None

    sh = _get_sheet_client()
    if not sh:
        return None

    try:
        logger.info("[sheets] Searching for all rows with run_id: %s", run_id_key)
        worksheet = sh.worksheet(SHEET_TAB_NAME)

        # Find all cells in Column A that match the run_id
        matching_cells = worksheet.findall(run_id_key, in_column=SHEET_KEY_COLUMN)

        if not matching_cells:
            logger.warning("[sheets] Could not find key '%s' in sheet.", run_id_key)
            return None

        answer_texts: List[str] = []
        # Get all values from the data column at once to reduce API calls
        all_data_col_values = worksheet.col_values(SHEET_DATA_COLUMN)

        for cell in matching_cells:
            # `cell.row` is 1-indexed, list is 0-indexed
            row_index = cell.row - 1
            if row_index < len(all_data_col_values):
                answer_text = all_data_col_values[row_index]
                if answer_text and isinstance(answer_text, str):
                    answer_texts.append(answer_text.strip())
            else:
                logger.warning(
                    "[sheets] Found cell at row %s but data column %s was short.",
                    cell.row,
                    SHEET_DATA_COLUMN,
                )

        if not answer_texts:
            logger.warning(
                "[sheets] Found rows for %s, but Column D was empty for all of them.",
                run_id_key,
            )
            return None

        # Join all answers into a single text block for the AI
        full_context = "\n".join(answer_texts)
        logger.info(
            "[sheets] Found %s answer segments for key %s.",
            len(answer_texts),
            run_id_key,
        )
        return full_context

    except Exception as e:
        logger.error("[sheets] Error while fetching from sheet: %s", e)

    return None


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


def _get_groq_client() -> Optional[Groq]:
    """Return a cached Groq client using GROQ_API_KEY from env, or None if missing."""
    global _GROQ_CLIENT_CACHE
    if _GROQ_CLIENT_CACHE is not None:
        return _GROQ_CLIENT_CACHE

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.warning("[groq] GROQ_API_KEY not set in environment; Groq fallback disabled.")
        return None

    try:
        _GROQ_CLIENT_CACHE = Groq(api_key=api_key)
        logger.info("[groq] Groq client initialized.")
        return _GROQ_CLIENT_CACHE
    except Exception as e:
        logger.error("[groq] Failed to initialize Groq client: %s", e, exc_info=True)
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


def _summarize_with_groq(prompt: str) -> Optional[Dict[str, Any]]:
    """
    Use Groq (Llama model) to generate a {title, description, hashtags} dict.
    Returns None on failure.
    """
    client = _get_groq_client()
    if client is None:
        return None

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.7,
            max_completion_tokens=512,
        )
        content = completion.choices[0].message.content or ""
        json_text = _extract_json(content)
        ai_data = json.loads(json_text)

        if isinstance(ai_data, dict) and "title" in ai_data:
            logger.info("[groq] Successfully generated AI captions.")
            return ai_data
        else:
            logger.warning("[groq] AI response was not a valid dict: %s", json_text)
            return None
    except Exception as e:
        logger.exception("[groq] Failed to generate content: %s", e)
        return None


def summarize_with_gemini(
    source_text: str, topic_hint: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Use Gemini to generate a {title, description, hashtags} dict.
    Will fall back to Groq if Gemini is out of quota or rate-limited.
    Returns None if everything fails.
    """
    api_key = _get_gemini_api_key()
    prompt = _build_caption_prompt(source_text, topic_hint)

    if not api_key:
        logger.warning("[gemini] No API key, cannot summarize. Falling back to Groq.")
        return _summarize_with_groq(prompt)

    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        logger.error("[gemini] Failed to configure model: %s", e)
        # If Gemini can't even configure, go straight to Groq
        return _summarize_with_groq(prompt)

    try:
        model_fallbacks = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
        ]
        response = generate_with_model_fallback(prompt, model_fallbacks)
        json_text = _extract_json(response.text)
        ai_data = json.loads(json_text)

        if isinstance(ai_data, dict) and "title" in ai_data:
            logger.info("[gemini] Successfully generated AI captions.")
            return ai_data
        else:
            logger.warning("[gemini] AI response was not a valid dict: %s", json_text)
            # Response was malformed – try Groq as a backup
            return _summarize_with_groq(prompt)
    except ResourceExhausted as e:
        logger.warning("[gemini] Quota exhausted, falling back to Groq: %s", e)
        return _summarize_with_groq(prompt)
    except Exception as e:
        msg = str(e).lower()
        if "quota" in msg or "rate limit" in msg or "429" in msg:
            logger.warning("[gemini] Quota-like error, falling back to Groq: %s", e)
            return _summarize_with_groq(prompt)
        logger.exception("[gemini] Failed to generate content: %s", e)
        return None


def _build_caption_prompt(source_text: str, topic_hint: Optional[str]) -> str:
    """
    Construct the shared JSON-style prompt used for both Gemini and Groq.
    """
    topic_prompt = f"The story is about: {topic_hint}\n" if topic_hint else ""

    prompt = f"""
    **Your Role:** You are a senior news analyst and editor for "RightSide Report," a news outlet with a strong conservative perspective.
    **Your Core Principles:** Your analysis is always guided by the principles of fiscal responsibility, limited government, individual liberty, and a strong national defense.
    **Your Task:** Analyze the following source text and generate a social media post that frames the story for your conservative audience. Find the angle that relates to our core principles.

    **Guidelines:**
    1.  **Find the Conservative Angle:** Do not just summarize. Re-frame the story to highlight its impact on the economy, taxes, government overreach, or individual freedoms.
    2.  **Use a Strong Tone:** Be direct, confident, and analytical.
    3.  **JSON Format:** The output MUST be in valid JSON.

    **SOURCE TEXT (KEY SENTENCES):**
    "{source_text}"

    {topic_prompt}

    **JSON FORMAT:**
    {{
      "title": "A concise, compelling title that frames the conservative angle (max 90 chars).",
      "description": "A short, engaging paragraph (2-3 sentences) that explains the story from our perspective, focusing on its impact on our core principles. For image posts, this can be the full text.",
      "hashtags": ["list", "of", "5", "relevant", "hashtags", "like", "Conservative", "LimitedGov", "Taxes"]
    }}
    """
    return prompt


# --- Main Public Function (unchanged API) ---


def get_title_description_tags(meta: Dict) -> Tuple[str, str, List[str]]:
    """
    Produce (title, description, hashtags_list) using meta + AI when helpful.
    This is the main function for main.py to call.
    """
    title = (meta.get("title") or meta.get("Title") or "").strip()
    description = (meta.get("description") or meta.get("Description") or "").strip()
    hashtags_raw = meta.get("hashtags") or meta.get("tags") or []
    hashtags_list = _coerce_hashtag_list(hashtags_raw)

    # --- NEW: Get Post Type ---
    post_type = meta.get("post_type", "video")  # Default to video

    # --- UPDATED LOGIC ---
    source: Optional[str] = None

    if post_type == "image":
        # For images, the text is already in the JSON.
        # We will use this text AS the description.
        logger.info("[caption] Image post type found. Using 'text' from JSON.")
        source = meta.get("text", "")
        # For images, the full text *is* the description
        description = source

        # We still generate a title and hashtags from this text
        needs_ai = True

    else:  # Video post logic
        needs_ai = _looks_generic(title) or _looks_generic(description) or not hashtags_list
        if needs_ai:
            logger.warning("[caption] Video captions look generic. Attempting AI gen.")
            article_key = meta.get("run_id") or meta.get("article_id") or meta.get("id")
            if not article_key:
                article_key = title

            if article_key:
                source = _get_answers_from_sheet(article_key)

            if not source:
                logger.warning("[caption] Could not find in Sheet, falling back to JSON.")
                source = (
                    meta.get("transcript")
                    or meta.get("summary")
                    or meta.get("text")
                    or description
                    or title
                    or ""
                )

    source = (source or "").strip()

    if needs_ai and source and not _looks_generic(source):
        ai_data = summarize_with_gemini(source, topic_hint=title)
        if ai_data:
            # Use AI data, falling back to meta data if a key is missing
            title = (ai_data.get("title") or title).strip()
            # For images, we want the *full text* as the description, not the AI summary.
            if post_type != "image":
                description = (ai_data.get("description") or description).strip()

            hashtags_list = _coerce_hashtag_list(ai_data.get("hashtags") or hashtags_list)
    else:
        logger.warning("[caption] No usable source text found for AI generation.")

    # Final cleanup and normalization
    if not title:
        title = "News Update"

    if not description:
        description = title

    if not hashtags_list:
        hashtags_list = ["News", "Politics", "BreakingNews"]

    final_tags = _normalize_hashtags(hashtags_list)

    final_title = title[:100]
    final_description = description[:5000]  # Use full text for images

    return final_title, final_description, final_tags
