# caption_utils.py
import json
import os
import logging
import re
from typing import Dict, Any, List, Tuple, Optional

import gspread # <-- IMPORT IS AT THE TOP
from google.cloud import secretmanager
import google.generativeai as genai
import google.auth

# --- ADD THIS HELPER FUNCTION ---
from google.api_core.exceptions import ResourceExhausted, InternalServerError

def generate_with_fallback(prompt, primary_model_name, fallback_model_name):
    """
    Tries to generate content with the primary model.
    If a rate limit error occurs, it falls back to the secondary model.
    """
    try:
        # 1. Try the primary model
        # print(f"Attempting with primary model: {primary_model_name}")
        model = genai.GenerativeModel(primary_model_name)
        return model.generate_content(prompt)
    except (ResourceExhausted, InternalServerError) as e:
        # 2. If rate limited, try the fallback
        print(f"⚠️  Rate limit on {primary_model_name}, trying fallback {fallback_model_name}. Error: {e}")
        try:
            model = genai.GenerativeModel(fallback_model_name)
            return model.generate_content(prompt)
        except Exception as fallback_e:
            print(f"❌ Fallback model {fallback_model_name} also failed.")
            raise fallback_e # Re-raise the fallback error
    except Exception as e:
        # 3. Handle other (non-rate-limit) errors
        print(f"❌ Non-rate-limit error on {primary_model_name}.")
        raise e # Re-raise the original error

# --- Caching and Helpers ---
_GEMINI_API_KEY_CACHE: Optional[str] = None
logger = logging.getLogger(__name__)

# --- Google Sheet Configuration ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/11lXogVfFS-VZWuVImTAfiZTDRc4v1LAmoTu9JR9y03U/edit"
SHEET_TAB_NAME = "AnswerSegment"
SHEET_KEY_COLUMN = 1  # Column A (run_id)
SHEET_DATA_COLUMN = 4 # Column D (sentence_text)
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
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file'
        ]
        creds, _ = google.auth.default(scopes=scopes)
        gc = gspread.authorize(creds)

        sh = gc.open_by_url(SHEET_URL)
        _SHEET_CLIENT_CACHE = sh
        logger.info("[sheets] Successfully connected to Google Sheet.")
        return sh
    except Exception as e:
        # Log the full error, including if it's a permissions issue
        logger.error(f"[sheets] Failed to connect to Google Sheet: {e}", exc_info=True)
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
        logger.info(f"[sheets] Searching for all rows with run_id: {run_id_key}")
        worksheet = sh.worksheet(SHEET_TAB_NAME)
        
        # Find all cells in Column A that match the run_id
        matching_cells = worksheet.findall(run_id_key, in_column=SHEET_KEY_COLUMN)
        
        if not matching_cells:
            logger.warning(f"[sheets] Could not find key '{run_id_key}' in sheet.")
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
                logger.warning(f"[sheets] Found cell at row {cell.row} but data column {SHEET_DATA_COLUMN} was short.")

        if not answer_texts:
            logger.warning(f"[sheets] Found rows for {run_id_key}, but Column D was empty for all of them.")
            return None
        
        # Join all answers into a single text block for the AI
        full_context = "\n".join(answer_texts)
        logger.info(f"[sheets] Found {len(answer_texts)} answer segments for key {run_id_key}.")
        return full_context
            
    except Exception as e:
        logger.error(f"[sheets] Error while fetching from sheet: {e}")
        
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
        # model = genai.GenerativeModel("models/gemini-1.5-flash") # <-- No longer need this
    except Exception as e:
        logger.error(f"[gemini] Failed to configure model: {e}")
        return None

    topic_prompt = f"The story is about: {topic_hint}\n" if topic_hint else ""
    
    prompt = f"""
    Analyze the following text, which contains several key sentences from a news article,
    and generate a social media post in valid JSON format.
    
    SOURCE TEXT (KEY SENTENCES):
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
        response = generate_with_fallback(
            prompt,
            primary_model_name='gemini-2.5-flash',    # <-- Updated primary model
            fallback_model_name='gemini-2.0-flash-lite' # <-- Added fallback
        )
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
        
        # --- THIS IS THE NEW LOGIC ---
        source = None
        
        # 1. Try to get source text from Google Sheet first
        #    Look for 'run_id' first, as seen in the sheet
        article_key = meta.get("run_id") or meta.get("article_id") or meta.get("id")
        if not article_key:
             # Fallback to title if no ID is present
             article_key = title
                
        if article_key:
            source = _get_answers_from_sheet(article_key)
        
        # 2. If Sheet fails, fall back to the old logic (text from JSON)
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
        source = str(source).strip()
        # --- END NEW LOGIC ---

        if source and not _looks_generic(source): # Don't send generic text to AI
            ai_data = summarize_with_gemini(source, topic_hint=title)
            if ai_data:
                # Use AI data, falling back to meta data if a key is missing
                title = (ai_data.get("title") or title).strip()
                description = (ai_data.get("description") or description).strip()
                hashtags_list = _coerce_hashtag_list(ai_data.get("hashtags") or hashtags_list)
        else:
            logger.warning("[caption] No usable source text found for AI generation.")

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