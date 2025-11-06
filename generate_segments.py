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
import time
import argparse
import datetime as dt
from typing import List, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import gspread
import google.generativeai as genai

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

def gs_client():
    return gspread.service_account(filename=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH"))

def open_sheet(sheet_key: str):
    return gs_client().open_by_key(sheet_key)

def read_active_questions(sh, tab="Questions") -> List[Tuple[str, str]]:
    rows = sh.worksheet(tab).get_all_records()
    return [(r["question_id"], r["question_text"]) for r in rows if str(r.get("enabled", "TRUE")).upper() == "TRUE"]

def append_rows_safe(ws, rows: List[List], batch_size: int = 100):
    for i in range(0, len(rows), batch_size):
        ws.append_rows(rows[i:i + batch_size], value_input_option="RAW")
        time.sleep(0.2)

# ========================= Gemini =========================

CONSERVATIVE_SYSTEM = (
    "You are providing news commentary. Based on the information provided, "
    "explain how a conservative commentator might interpret this event. "
    "Speak directly about the facts and events - never mention 'the article', 'the report', or 'the post'. "
    "Do not use phrases like 'Breaking News', 'Live from', or location tags. "
    "Use calm, non-inflammatory language. Answer in 2–3 sentences that flow naturally into a video."
)
NEUTRAL_SYSTEM = (
    "You are providing news commentary. Give a neutral, factual explanation in 2–3 sentences. "
    "Speak directly about what happened - never mention 'the article', 'the report', or 'the post'. "
    "Do not use phrases like 'Breaking News', 'Live from', or location tags. "
    "Write sentences that flow naturally together in a video."
)

def get_photo_url_for_question(question_text: str, answer_text: str, question_id: str, fallback_url: str = "") -> str:
    """
    Get a relevant stock photo from Pexels based on the question and answer.
    Falls back to broader topics or previous photo if specific search fails.
    """
    if pexels_photos is None:
        print("⚠️ pexels_photos module not available")
        return ""
    
    try:
        print(f"  📸 Finding stock photo for {question_id}...")
        photo_url = pexels_photos.get_photo_for_question(question_text, answer_text, fallback_url)
        return photo_url
    except Exception as e:
        print(f"  ⚠️ Error fetching stock photo: {e}")
        return fallback_url if fallback_url else ""

def gemini_answer(question: str, article: str, conservative: bool, model_name: str) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        # Mock for local wiring tests without a key
        return ("From a conservative perspective, the emphasis is on limited government and accountability."
                if conservative else
                "This is a concise neutral summary based on early reporting.")
    try:
        genai.configure(api_key=key)
        system = CONSERVATIVE_SYSTEM if conservative else NEUTRAL_SYSTEM
        prompt = f"{system}\n\nNews Information:\n{article}\n\nQuestion:\n{question}\n\nYour Report:"
        model = genai.GenerativeModel(model_name)
        # Light retry guard
        for attempt in range(2):
            try:
                resp = model.generate_content(prompt)
                txt = (resp.text or "").strip()
                if txt:
                    return txt
            except Exception as e:
                if attempt == 0:
                    time.sleep(0.6)
                else:
                    raise e
        return "A brief neutral summary could not be generated."
    except Exception:
        return ("A brief neutral summary based on public reporting. Details are evolving."
                if not conservative else
                "From a conservative perspective, commentators would emphasize personal responsibility and limited government.")

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
    ap.add_argument("--model", default="gemini-2.5-flash", help="Gemini model")

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

    if not url:
        sys.exit("No story URL provided. Use --auto or pass --story_url.")

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
    
    for qid, qtext in questions:
        conservative = (qid == "conservative_angle") or ("conservative" in qid.lower())
        answer = gemini_answer(qtext, article, conservative, model_name=args.model)
        sents = limit_sentences_length(to_sentences(answer), max_words=args.max_words, min_words=args.min_words)
        
        # Get one stock photo URL per question (using the full answer for context)
        # Pass the last successful photo as a fallback
        image_url = get_photo_url_for_question(qtext, answer, qid, last_successful_photo)
        
        # Track successful photos for fallback
        if image_url:
            last_successful_photo = image_url
        
        for idx, sent in enumerate(sents):
            # Use the same image URL for all segments of this question
            img_path = image_url if not args.image_path_prefix else f"{args.image_path_prefix}{run_id}_{qid}_{idx}.png"
            rows_to_append.append([run_id, qid, idx, sent, img_path, args.duration])

    # Write segments
    ws_segments = sh.worksheet("AnswerSegments")
    append_rows_safe(ws_segments, rows_to_append)

    # Write run row (best-effort)
    try:
        sh.worksheet("Runs").append_rows([[
            run_id, url, title or "", dt.datetime.utcnow().isoformat() + "Z", 0.0
        ]], value_input_option="RAW")
    except Exception:
        pass

    print(f"✅ Wrote {len(rows_to_append)} sentence segments for run {run_id}")

if __name__ == "__main__":
    main()
