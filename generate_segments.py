#!/usr/bin/env python3
"""
generate_segments.py

Features:
- (--auto) Pick the most popular/recency-weighted article via news_picker.pick_top_story()
  (NewsData.io under the hood). Defaults to politics.
- Otherwise use --story_url / --story_title
- Fetch article text with fallbacks (normal -> Reuters AMP -> reader mirror)
- (Optional) --article_text to bypass fetching
- Use Google Gemini to answer each question (incl. conservative_angle) in 2–3 sentences
- Split answers into short, display-ready sentences (max words) and write to AnswerSegments
- Append one row to Runs

Google Sheet tabs expected:
  Questions(question_id, question_text, enabled)
  Runs(run_id, story_url, story_title, published_at, popularity_score)
  AnswerSegments(run_id, question_id, sentence_index, sentence_text, image_path, duration_sec)
"""

import os
import sys
import re
import time # This was already here, which is good.
import argparse
import datetime as dt
import json
import random
from typing import List, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import gspread
import google.generativeai as genai
from gspread.exceptions import APIError
from google.api_core.exceptions import ResourceExhausted, InternalServerError


# The new fallback function to use in all 3 files
# (Remember to add "import time" at the top of each file!)
def generate_with_model_fallback(prompt: str, model_list: list[str]):
    """
    Tries to generate content with a list of models, falling back on quota errors.
    """
    if not model_list:
        raise ValueError("Model list cannot be empty.")
    
    last_error = None
    
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
                print(f"❌ All fallback models are also rate-limited. Raising error.")
                raise e
            continue # Try next model
        
        except (InternalServerError) as e:
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
                continue # Try next model
                
        except Exception as e:
            # Other error (Safety, etc.). Try the next model immediately.
            print(f"❌ Non-quota error on {model_name}: {e}. Trying next model...")
            last_error = e
            if is_last_model:
                print(f"❌ All fallback models also failed. Raising error.")
                raise e
            continue # Try next model
    
    # This should not be reachable, but as a safeguard
    if last_error:
        raise last_error
    else:
        raise Exception("Failed to generate content after trying all models.")

# Auto-pick support (NewsData.io). Ensure news_picker.py is in the same folder.
try:
    import news_picker  # provides pick_top_story(country, category, query)
except Exception:
    news_picker = None  # we'll guard in --auto path

# Pexels stock photos
try:
    import pexels_photos  # provides get_photo_for_question()
except Exception:
    pexels_photos = None

def save_article_data(url: str, title: str):
    """Save the picked article's data to a JSON file for other scripts to use."""
    data = {"url": url, "title": title}
    output_path = "generated/article.json"
    os.makedirs("generated", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"✅ Article data saved to {output_path}")

# ========================= Sentence utils =========================

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

def now_run_id() -> str:
    return dt.datetime.utcnow().strftime("run-%Y%m%dT%H%M%SZ")

def to_sentences(text: str) -> List[str]:
    """Split text into sentences, handling bullets and fragments."""
    if not text:
        return []
    
    # Remove bullet points and line breaks that break sentences
    text = re.sub(r'\n\s*[\*\-•]\s*', ' ', text)  # Replace bullet points with space
    text = re.sub(r'\n+', ' ', text)  # Replace newlines with space
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    
    return [p.strip() for p in SENT_SPLIT.split(text.strip()) if p.strip()]

def wrap_sentence_to_word_limit(sent: str, max_words: int) -> List[str]:
    """Split long sentences into chunks of max_words."""
    words = sent.split()
    if len(words) <= max_words:
        return [sent]
    out, i = [], 0
    while i < len(words):
        chunk = " ".join(words[i:i + max_words]).strip().rstrip(",;: ")
        if chunk:
            out.append(chunk)
        i += max_words
    return out

def limit_sentences_length(sents: List[str], max_words: int, min_words: int = 10) -> List[str]:
    """
    Make sentences more consistent in length for better video display.
    - Splits long sentences (> max_words)
    - Combines short sentences (< min_words) with the next one
    - Ensures each chunk is readable and fits on screen
    """
    out = []
    buffer = []  # Hold short sentences to combine
    
    for s in sents:
        words = s.split()
        word_count = len(words)
        
        # If sentence is too long, split it
        if word_count > max_words:
            # First, flush any buffered short sentences
            if buffer:
                combined = " ".join(buffer)
                out.append(combined)
                buffer = []
            
            # Split the long sentence
            chunks = wrap_sentence_to_word_limit(s, max_words)
            out.extend(chunks)
        
        # If sentence is too short, buffer it to combine with next
        elif word_count < min_words:
            buffer.append(s)
            
            # If buffer is getting long enough, flush it
            buffered_words = sum(len(b.split()) for b in buffer)
            if buffered_words >= min_words:
                combined = " ".join(buffer)
                if len(combined.split()) <= max_words:
                    out.append(combined)
                    buffer = []
                else:
                    # Buffer got too big, split it
                    out.extend(wrap_sentence_to_word_limit(combined, max_words))
                    buffer = []
        
        # Sentence is just right
        else:
            # Flush buffer first if exists
            if buffer:
                combined = " ".join(buffer)
                if len(combined.split()) <= max_words:
                    out.append(combined)
                else:
                    out.extend(wrap_sentence_to_word_limit(combined, max_words))
                buffer = []
            
            out.append(s)
    
    # Flush any remaining buffer
    if buffer:
        combined = " ".join(buffer)
        if len(combined.split()) <= max_words:
            out.append(combined)
        else:
            out.extend(wrap_sentence_to_word_limit(combined, max_words))
    
    return [x for x in out if x]

# ========================= Fetch with fallbacks =========================

def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    main = soup.find(["article", "main"]) or soup
    return " ".join(main.get_text(" ").split())[:12000]

def _try_get(url: str, timeout=20) -> str:
    headers = {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/129.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "close",
    }
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text

def _reuters_amp(url: str) -> str:
    try:
        u = urlparse(url)
        if "reuters.com" not in u.netloc:
            return ""
        path = u.path
        if not path.endswith("/amp"):
            path = path.rstrip("/") + "/amp"
        amp_url = urlunparse((u.scheme, u.netloc, path, u.params, u.query, u.fragment))
        return _try_get(amp_url)
    except Exception:
        return ""

def fetch_article_text(url: str, timeout: int = 20) -> str:
    # 1) Normal fetch
    try:
        html = _try_get(url, timeout=timeout)
        print("fetch: normal")
        return _clean_text(html)
    except Exception as e1:
        print(f"fetch: normal failed: {e1}")

    # 2) Reuters AMP fallback
    try:
        if "reuters.com" in url:
            html = _reuters_amp(url)
            if html:
                print("fetch: reuters amp")
                return _clean_text(html)
    except Exception as e2:
        print(f"fetch: amp failed: {e2}")

    # 3) Reader mirror fallback (plain-text proxy)
    try:
        mirror = f"https://r.jina.ai/http://{url}"
        r = requests.get(mirror, timeout=timeout)
        r.raise_for_status()
        text = " ".join(r.text.split())
        if len(text) > 200:
            print("fetch: reader mirror")
            return text[:12000]
    except Exception as e3:
        print(f"fetch: mirror failed: {e3}")

    return f"(Fetch failed for {url})"

# ========================= Env & Sheets =========================

def load_env_or_die():
    load_dotenv(".env")
    sheet_key = os.getenv("GOOGLE_SHEETS_KEY")
    creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")
    gemini_key = os.getenv("GEMINI_API_KEY")  # optional mock mode if absent
    if not sheet_key:
        sys.exit("GOOGLE_SHEETS_KEY missing in .env")
    if not creds_path or not os.path.exists(creds_path):
        sys.exit("Service account key not found at GOOGLE_SERVICE_ACCOUNT_JSON_PATH")
    return sheet_key, creds_path, gemini_key

def _parse_status_code_from_apierror(err: APIError) -> int:
    """Best-effort to extract HTTP status code from gspread APIError."""
    try:
        code = getattr(err, "response", None)
        if code is not None:
            sc = getattr(code, "status_code", None)
            if sc:
                return int(sc)
    except Exception:
        pass
    # Fallback to parsing string contents like ***'code': 503, ...***
    try:
        import re as _re
        m = _re.search(r"'code':\s*(\d+)", str(err))
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0

def _with_retry(call, *, retries: int = 6, base_delay: float = 0.6, retriable_statuses=(429, 500, 502, 503, 504)):
    """
    Execute `call` with exponential backoff for common transient Google Sheets errors.
    - Retries on gspread.APIError with status in retriable_statuses
    - Also retries on requests-related network errors
    """
    for attempt in range(retries):
        try:
            return call()
        except APIError as e:
            code = _parse_status_code_from_apierror(e)
            if code in retriable_statuses and attempt < retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.25)
                print(f"  ⏳ Sheets API {code}; retrying in {delay:.2f}s (attempt {attempt+1}/{retries})")
                time.sleep(delay)
                continue
            raise
        except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as e:
            if attempt < retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.25)
                print(f"  ⏳ Network error; retrying in {delay:.2f}s (attempt {attempt+1}/{retries}) - {e}")
                time.sleep(delay)
                continue
            raise

def gs_client():
    return gspread.service_account(filename=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH"))

def open_sheet(sheet_key: str):
    # Opening can occasionally 503 as well
    return _with_retry(lambda: gs_client().open_by_key(sheet_key))

def read_active_questions(sh, tab="Questions") -> List[Tuple[str, str]]:
    ws = _with_retry(lambda: sh.worksheet(tab))
    rows = _with_retry(lambda: ws.get_all_records())
    return [(r["question_id"], r["question_text"]) for r in rows if str(r.get("enabled", "TRUE")).upper() == "TRUE"]

def append_rows_safe(ws, rows: List[List], batch_size: int = 100):
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        _with_retry(lambda: ws.append_rows(chunk, value_input_option="RAW"))
        time.sleep(0.2)

# ========================= Gemini =========================

# --- THIS IS THE ONLY SYSTEM PROMPT NOW ---
CONSERVATIVE_SYSTEM = (
    "You are a news analyst for 'RightSide Report,' a conservative news outlet. "
    "Your analysis is guided by fiscal responsibility, limited government, and individual liberty. "
    "Re-frame the story to highlight its impact on the economy, taxes, or government overreach. "
    "Speak directly about the facts. NEVER mention 'the article' or 'the report'. "
    "Your tone is direct, analytical, and confident. "
    "Answer in 2-3 short, clear sentences suitable for a video segment."
)
# --- NEUTRAL_SYSTEM variable has been deleted ---


def suggest_photo_search_terms(answer_text: str, article_text: str, model_name: str) -> str:
    """
    Use Gemini AI to suggest appropriate photo search terms based on the answer and article content.
    Returns a 2-4 word search phrase for stock photos.
    """
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        # Fallback to simple keyword extraction
        return ""
    
    try:
        genai.configure(api_key=key)
        prompt = f"""You are helping select stock photos for a political news video. Based on the answer and article context below, suggest 2-4 words for a stock photo search.

Answer: {answer_text[:300]}

Article Context: {article_text[:500]}

RULES FOR PHOTO SUGGESTIONS:
1. For political topics: suggest "capitol building", "government chamber", "political debate", "voting booth", "american flag"
2. For policy/law topics: suggest "courthouse steps", "legal documents", "congressional hearing", "government officials"
3. For economic topics: suggest "financial district", "stock market", "business meeting", "economic data"
4. For military/security: suggest "military honor guard", "border patrol", "defense officials", "security personnel"
5. For social issues: suggest "diverse community", "town hall meeting", "public gathering", "city street"
6. AVOID: medical imagery, vaccines, healthcare if the topic is about politics/policy
7. AVOID: abstract concepts - stay concrete and photographable
8. AVOID: controversial or sensitive imagery

Choose terms that are professional, neutral, and visually represent the political/policy nature of the content.

Photo search terms (2-4 words only):"""
        
        # The primary model is passed in, then fallbacks
        model_fallbacks = [
            model_name, 
            "gemini-2.0-flash", 
            "gemini-2.0-flash-lite"
        ]
        resp = generate_with_model_fallback(prompt, model_fallbacks)
        suggestion = (resp.text or "").strip().strip('"').strip("'")
        
        # Clean up the response - take only first line and limit words
        suggestion = suggestion.split('\n')[0].strip()
        words = suggestion.split()[:4]  # Max 4 words
        suggestion = " ".join(words)
        
        # Filter out inappropriate terms
        inappropriate_terms = ['vaccine', 'syringe', 'needle', 'medical', 'doctor', 'hospital', 'clinic']
        suggestion_lower = suggestion.lower()
        if any(term in suggestion_lower for term in inappropriate_terms):
            print(f"  ⚠️ Filtered inappropriate AI suggestion: '{suggestion}'")
            return ""
        
        if suggestion and len(suggestion) > 3:
            print(f"  🤖 AI suggested photo search: '{suggestion}'")
            return suggestion
        
        return ""
    except Exception as e:
        print(f"  ⚠️ AI photo suggestion failed: {e}")
        return ""

def get_photo_url_for_answer(answer_text: str, article_text: str, question_id: str, model_name: str, fallback_url: str = "") -> str:
    """
    Get a relevant stock photo from Pexels based on the answer content.
    Uses AI to suggest appropriate search terms, then falls back to keyword extraction.
    """
    if pexels_photos is None:
        print("⚠️ pexels_photos module not available")
        return ""
    
    try:
        print(f"  📸 Finding stock photo for {question_id}...")
        
        # First, try AI-suggested search terms
        ai_suggestion = suggest_photo_search_terms(answer_text, article_text, model_name)
        if ai_suggestion:
            photo = pexels_photos.search_pexels_photo(ai_suggestion, per_page=30, orientation="portrait")
            if photo:
                print(f"  ✅ Using AI-suggested photo")
                return photo["url"]
        
        # Fallback to keyword extraction method
        photo_url = pexels_photos.get_photo_for_answer(answer_text, article_text, fallback_url)
        return photo_url
    except Exception as e:
        print(f"  ⚠️ Error fetching stock photo: {e}")
        return fallback_url if fallback_url else ""

# --- THIS FUNCTION IS NOW SIMPLER ---
def gemini_answer(question: str, article: str, model_name: str) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        # Mock for local wiring tests without a key
        return ("From a conservative perspective, the emphasis is on limited government and accountability.")

    try:
        genai.configure(api_key=key)
        # It now *always* uses CONSERVATIVE_SYSTEM
        prompt = f"{CONSERVATIVE_SYSTEM}\n\nNews Information:\n{article}\n\nQuestion:\n{question}\n\nYour Report:"
        
        # The primary model is passed in, then fallbacks
        model_fallbacks = [
            model_name, # This will be "gemini-2.5-flash" from the workflow
            "gemini-2.0-flash", 
            "gemini-2.0-flash-lite"
        ]
        resp = generate_with_model_fallback(prompt, model_fallbacks)
        txt = (resp.text or "").strip()
        if txt:
            return txt
        return "A brief summary could not be generated."
    except Exception:
        # Simplified fallback
        return "A brief summary based on public reporting. Details are evolving."

# ========================= Main =========================

def main():
    ap = argparse.ArgumentParser(description="Auto-pick top story (optional) and generate sentence segments with Gemini.")
    # Auto-pick options (default to politics focus)
    ap.add_argument("--auto", action="store_true", help="Auto-select the most popular article now")
    ap.add_argument("--country", default="us", help="Country code for headlines")
    ap.add_argument("--topic", default="politics", help="Category/topic (e.g., politics, business, technology)")
    ap.add_argument("--query", default="", help="Optional search keywords to bias selection")

    # Manual URL / content
    ap.add_argument("--story_url", default="", help="News article URL (ignored if --auto)")
    ap.add_argument("--story_title", default="", help="Optional title for Runs tab")
    ap.add_argument("--article_text", default="", help="Override: raw article text")

    # Output / model settings
    ap.add_argument("--duration", type=float, default=4.0, help="Seconds each sentence is shown")
    ap.add_argument("--image-path-prefix", default="", help="Prefix to pre-fill image_path")
    ap.add_argument("--max-words", type=int, default=15, help="Max words per sentence")
    ap.add_argument("--min-words", type=int, default=10, help="Min words per sentence (combine shorter ones)")
    
    # --- THIS IS THE FIX ---
    ap.add_argument("--model", default="gemini-2.0-flash", help="Gemini model") # <-- FIXED DEFAULT
    # -----------------------

    args = ap.parse_args()
    sheet_key, _, _ = load_env_or_die()

    # Auto-pick article (NewsData.io via news_picker)
    title = args.story_title
    url = args.story_url
    if args.auto:
        if news_picker is None:
            sys.exit("news_picker.py not found. Add it next to this script or disable --auto.")
        picked = news_picker.pick_top_story(
            country=args.country, category=args.topic, query=(args.query or None)
        )
        if not picked:
            sys.exit("Could not pick a top story. Check NEWSDATA_API_KEY or adjust --country/--topic/--query.")
        url, title, published_at, score = picked
        print(f"[auto] Picked: {title} ({url}) score={score:.3f} published={published_at.isoformat()}Z")
        save_article_data(url, title) # This was already in your new file, which is great

    if not url:
        sys.exit("No story URL provided. Use --auto or pass --story_url.")
    
    # --- ENSURE 'generated' FOLDER EXISTS ---
    # This is run by the workflow, but good to have here too
    os.makedirs("generated", exist_ok=True) 
    # ----------------------------------------

    # Open sheet & ensure tabs
    sh = open_sheet(sheet_key)
    titles = {ws.title for ws in sh.worksheets()}
    for tab in ("Questions", "Runs", "AnswerSegments"):
        if tab not in titles:
            sys.exit(f"Missing required tab: {tab}")
    questions = read_active_questions(sh)
    if not questions:
        sys.exit("No active questions in Questions tab (enabled != TRUE).")

    # Get article text
    if args.article_text:
        article = args.article_text[:12000]
        print("article: override text")
    else:
        article = fetch_article_text(url)

    # Generate answers -> sentences -> rows
    run_id = now_run_id()
    rows_to_append = []
    last_successful_photo = ""  # Track last successful photo for fallback
    
    gemini_request_count = 0
    for qid, qtext in questions:
        # --- LOGIC IS NOW SIMPLER ---
        # No more 'conservative' boolean check. Just call the function.
        answer = gemini_answer(qtext, article, model_name=args.model)
        gemini_request_count += 1
        
        sents = limit_sentences_length(to_sentences(answer), max_words=args.max_words, min_words=args.min_words)
        image_url = get_photo_url_for_answer(answer, article, qid, args.model, last_successful_photo)
        if image_url:
            last_successful_photo = image_url
            
        for idx, sent in enumerate(sents):
            img_path = image_url if not args.image_path_prefix else f"{args.image_path_prefix}{run_id}_{qid}_{idx}.png"
            rows_to_append.append([run_id, qid, idx, sent, img_path, args.duration])
            
        if gemini_request_count % 4 == 0 and gemini_request_count < len(questions):
            print("⏳ Pausing for 60 seconds to avoid Gemini rate limit...")
            time.sleep(60)
            
    # Write segments
    ws_segments = _with_retry(lambda: sh.worksheet("AnswerSegments"))
    append_rows_safe(ws_segments, rows_to_append)

    # Write run row (best-effort)
    try:
        ws_runs = _with_retry(lambda: sh.worksheet("Runs"))
        _with_retry(lambda: ws_runs.append_rows([[
            run_id, url, title or "", dt.datetime.utcnow().isoformat() + "Z", 0.0
        ]], value_input_option="RAW"))
    except Exception:
        pass

    print(f"✅ Wrote {len(rows_to_append)} sentence segments for run {run_id}")

    # --- ADDED: SAVE THE RUN_ID FOR OTHER SCRIPTS ---
    try:
        with open("generated/run_id.txt", "w", encoding="utf-8") as f:
            f.write(run_id)
        print(f"✅ Saved run_id to generated/run_id.txt")
    except Exception as e:
        print(f"⚠️  Could not save run_id.txt: {e}")
    # -------------------------------------------------

if __name__ == "__main__":
    main()