#!/usr/bin/env python3
"""
generate_segments.py

Features:
- (--auto) Pick the most popular/recency-weighted article via news_picker.pick_top_story()
  (NewsData.io under the hood). Defaults to politics.
- Uses AI to check the core topic of the picked story against the last 3 stories
  in the Runs tab to prevent running on the same major topic repeatedly.
- Otherwise use --story_url / --story_title
- Fetch article text with fallbacks (normal -> Reuters AMP -> reader mirror)
- Use Google Gemini (with Groq fallback) to answer each question in 2–3 sentences
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
import json
import random
from typing import List, Tuple, Dict, Any
from urllib.parse import urlparse, urlunparse
import urllib.request

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import gspread
import google.generativeai as genai
from gspread.exceptions import APIError
from google.api_core.exceptions import ResourceExhausted, InternalServerError


# --------------------------------------------------------------------
# Groq helper + unified Gemini→Groq fallback
# --------------------------------------------------------------------

def _call_groq_chat(prompt: str) -> str | None:
    """Call Groq's chat completions API and return the content string, or None on failure."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[groq] GROQ_API_KEY not set; skipping Groq fallback.")
        return None

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a conservative-leaning news analyst. "
                    "You answer questions about a news article in short, clear sentences. "
                    "Always respond directly to the user's prompt."
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8")
        parsed = json.loads(payload)
        choices = parsed.get("choices") or []
        if not choices:
            print("[groq] No choices in response.")
            return None
        msg = choices[0].get("message", {})
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content)
        return str(content)
    except Exception as e:
        print(f"[groq] Groq API call failed: {e}")
        return None


class _SimpleResponse:
    """Tiny wrapper so Groq text looks like a Gemini response (has .text)."""
    def __init__(self, text: str):
        self.text = text


def generate_with_model_fallback(prompt: str, model_list: list[str]):
    """
    Tries to generate content with a list of Gemini models, then falls back to Groq
    if all Gemini models are exhausted (e.g. 429 quota errors).
    """
    if not model_list:
        raise ValueError("Model list cannot be empty.")

    last_error: Exception | None = None

    # First: try Gemini models in order
    for model_name in model_list:
        try:
            print(f"ℹ️  Attempting Gemini generation with: {model_name}")
            model = genai.GenerativeModel(model_name)
            return model.generate_content(prompt)

        except ResourceExhausted as e:
            print(f"⚠️  Quota limit on {model_name}. Trying next Gemini model...")
            last_error = e
            continue

        except InternalServerError as e:
            print(f"⚠️  Server error on {model_name}. Pausing for 10s and retrying...")
            last_error = e
            time.sleep(10)
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt)
            except Exception as retry_e:
                print(f"❌ Retry failed for {model_name}. Trying next Gemini model...")
                last_error = retry_e
                continue

        except Exception as e:
            print(f"❌ Non-quota error on {model_name}: {e}. Trying next Gemini model...")
            last_error = e
            continue

    # If we reach here, all Gemini models failed
    print("🔁 All Gemini models failed or are rate-limited. Trying Groq as backup...")
    groq_text = _call_groq_chat(prompt)
    if groq_text:
        print("✅ Groq fallback succeeded.")
        return _SimpleResponse(groq_text)

    print("❌ Groq fallback also failed.")
    if last_error:
        raise last_error
    raise Exception("Failed to generate content after trying Gemini and Groq.")


# --------------------------------------------------------------------
# Auto-pick support (NewsData.io). Ensure news_picker.py is in the same folder.
# --------------------------------------------------------------------

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

    text = re.sub(r'\n\s*[\*\-•]\s*', ' ', text)
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\s+', ' ', text)

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
    """
    out = []
    buffer = []

    for s in sents:
        words = s.split()
        word_count = len(words)

        if word_count > max_words:
            if buffer:
                combined = " ".join(buffer)
                out.append(combined)
                buffer = []

            chunks = wrap_sentence_to_word_limit(s, max_words)
            out.extend(chunks)

        elif word_count < min_words:
            buffer.append(s)
            buffered_words = sum(len(b.split()) for b in buffer)
            if buffered_words >= min_words:
                combined = " ".join(buffer)
                if len(combined.split()) <= max_words:
                    out.append(combined)
                    buffer = []
                else:
                    out.extend(wrap_sentence_to_word_limit(combined, max_words))
                    buffer = []

        else:
            if buffer:
                combined = " ".join(buffer)
                if len(combined.split()) <= max_words:
                    out.append(combined)
                else:
                    out.extend(wrap_sentence_to_word_limit(combined, max_words))
                buffer = []
            out.append(s)

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
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/129.0.0.0 Safari/537.36"
        ),
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
    try:
        html = _try_get(url, timeout=timeout)
        print("fetch: normal")
        return _clean_text(html)
    except Exception as e1:
        print(f"fetch: normal failed: {e1}")

    try:
        if "reuters.com" in url:
            html = _reuters_amp(url)
            if html:
                print("fetch: reuters amp")
                return _clean_text(html)
    except Exception as e2:
        print(f"fetch: amp failed: {e2}")

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
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not sheet_key:
        sys.exit("GOOGLE_SHEETS_KEY missing in .env")
    if not creds_path or not os.path.exists(creds_path):
        sys.exit("Service account key not found at GOOGLE_SERVICE_ACCOUNT_JSON_PATH")
    return sheet_key, creds_path, gemini_key


def _parse_status_code_from_apierror(err: APIError) -> int:
    try:
        code = getattr(err, "response", None)
        if code is not None:
            sc = getattr(code, "status_code", None)
            if sc:
                return int(sc)
    except Exception:
        pass
    try:
        import re as _re
        m = _re.search(r"'code':\s*(\d+)", str(err))
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


def _with_retry(call, *, retries: int = 6, base_delay: float = 0.6,
                retriable_statuses=(429, 500, 502, 503, 504)):
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
    return _with_retry(lambda: gs_client().open_by_key(sheet_key))


def read_active_questions(sh, tab="Questions") -> List[Tuple[str, str]]:
    ws = _with_retry(lambda: sh.worksheet(tab))
    rows = _with_retry(lambda: ws.get_all_records())
    return [
        (r["question_id"], r["question_text"])
        for r in rows
        if str(r.get("enabled", "TRUE")).upper() == "TRUE"
    ]


def append_rows_safe(ws, rows: List[List], batch_size: int = 100):
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        _with_retry(lambda: ws.append_rows(chunk, value_input_option="RAW"))
        time.sleep(0.2)


# ========================= AI Deduplication =========================

def get_recent_runs_dedupe(sh, num_past: int = 12) -> Tuple[set[str], set[str]]:
    """Return (recent_canonical_urls, recent_title_fingerprints) from the Runs sheet.

    This makes dedupe work even when local `.used.txt` is missing (e.g., CI/Cloud runs).
    """
    try:
        if news_picker is None:
            return set(), set()
        ws_runs = _with_retry(lambda: sh.worksheet("Runs"))
        all_values = _with_retry(lambda: ws_runs.get_all_values())
        if not all_values or len(all_values) < 2:
            return set(), set()

        rows = all_values[1:]
        rows = rows[-num_past:]

        urls: set[str] = set()
        titlefps: set[str] = set()

        for r in rows:
            # Runs columns: run_id, story_url, story_title, published_at, popularity_score
            story_url = (r[1] if len(r) > 1 else "") or ""
            story_title = (r[2] if len(r) > 2 else "") or ""
            c = news_picker.canonicalize_url(story_url)
            if c:
                urls.add(c)
            fp = news_picker.title_fingerprint(story_title)
            if fp:
                titlefps.add(fp)
        return urls, titlefps
    except Exception as e:
        print(f"  ⚠️ Could not read Runs for dedupe: {e}")
        return set(), set()

def get_past_topics(sh, num_past: int = 3, model_name: str = "gemini-2.5-flash") -> List[str]:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("  ⚠️ Skipping past topic analysis: GEMINI_API_KEY is missing.")
        return []

    try:
        genai.configure(api_key=key)
        ws_runs = _with_retry(lambda: sh.worksheet("Runs"))

        all_values = _with_retry(lambda: ws_runs.get_all_values())
        if not all_values or len(all_values) < 2:
            return []

        past_titles = [row[2] for row in all_values[1:]][-num_past:]
        past_titles.reverse()

        if not past_titles:
            return []

        print(f"🔎 Analyzing last {len(past_titles)} stories for topic duplication...")

        title_list = "\n".join([f"- {title}" for title in past_titles])
        prompt = f"""Analyze the following list of recent news article titles.
For each title, extract the core subject matter and return it as a single, three-word phrase.
Return ONLY a comma-separated list of the three-word phrases.

Titles:
{title_list}

Example: "Explosive new documents reveal a House Democrat received real-time coaching from convicted criminal Jeffrey Epstein..." -> Epstein Democrat coaching
Example: "Senate passes $95 billion aid package for Ukraine and Israel" -> Foreign aid vote

Comma-separated list of 3-word topics:"""

        model_fallbacks = [model_name, "gemini-2.0-flash", "gemini-2.0-flash-lite"]
        resp = generate_with_model_fallback(prompt, model_fallbacks)
        topic_string = (resp.text or "").strip()
        topics = [t.strip().lower() for t in topic_string.split(',') if t.strip()]

        print(f"  🧠 Past Topics: {topics}")
        return topics

    except Exception as e:
        print(f"  ⚠️ Error fetching or processing past topics: {e}")
        return []


def get_current_topic(article_text: str, model_name: str) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return ""

    try:
        genai.configure(api_key=key)
        prompt = f"""Analyze the following article text.
Extract the core subject matter and return it as a single, three-word phrase suitable for comparison.
Return ONLY the three-word phrase.

Article text (first 500 characters): {article_text[:500]}

Three-word topic:"""

        model_fallbacks = [model_name, "gemini-2.0-flash", "gemini-2.0-flash-lite"]
        resp = generate_with_model_fallback(prompt, model_fallbacks)
        topic = (resp.text or "").strip().lower()
        print(f"  🧠 New Article Topic: {topic}")
        return topic
    except Exception as e:
        print(f"  ⚠️ Error generating current topic: {e}")
        return ""


def is_topic_duplicate(new_topic: str, past_topics: List[str], similarity_threshold: int = 2) -> bool:
    if not new_topic:
        return False

    new_words = set(new_topic.split())
    for past_topic in past_topics:
        past_words = set(past_topic.split())
        overlap = len(new_words.intersection(past_words))
        if overlap >= similarity_threshold:
            print(f"  ❌ DUPLICATE DETECTED: New topic '{new_topic}' overlaps with past topic '{past_topic}' ({overlap} words).")
            return True

    return False


# ========================= Gemini Answer & Photos =========================

CONSERVATIVE_SYSTEM = (
    "You are a news analyst for 'RightSide Report,' a conservative news outlet. "
    "Your analysis is guided by fiscal responsibility, limited government, and individual liberty. "
    "Re-frame the story to highlight its impact on the economy, taxes, or government overreach. "
    "Speak directly about the facts. NEVER mention 'the article' or 'the report'. "
    "Your tone is direct, analytical, and confident. "
    "Answer in 2-3 short, clear sentences suitable for a video segment."
)


def suggest_photo_search_terms(answer_text: str, article_text: str, model_name: str) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
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

        model_fallbacks = [model_name, "gemini-2.0-flash", "gemini-2.0-flash-lite"]
        resp = generate_with_model_fallback(prompt, model_fallbacks)
        suggestion = (resp.text or "").strip().strip('"').strip("'")

        suggestion = suggestion.split('\n')[0].strip()
        words = suggestion.split()[:4]
        suggestion = " ".join(words)

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


def get_photo_url_for_answer(answer_text: str, article_text: str, question_id: str,
                             model_name: str, fallback_url: str = "") -> str:
    if pexels_photos is None:
        print("⚠️ pexels_photos module not available")
        return ""

    try:
        print(f"  📸 Finding stock photo for {question_id}...")
        ai_suggestion = suggest_photo_search_terms(answer_text, article_text, model_name)
        if ai_suggestion:
            photo = pexels_photos.search_pexels_photo(ai_suggestion, per_page=30, orientation="portrait")
            if photo:
                print("  ✅ Using AI-suggested photo")
                return photo["url"]

        photo_url = pexels_photos.get_photo_for_answer(answer_text, article_text, fallback_url)
        return photo_url
    except Exception as e:
        print(f"  ⚠️ Error fetching stock photo: {e}")
        return fallback_url if fallback_url else ""


def gemini_answer(question: str, article: str, model_name: str) -> str:
    key = os.getenv("GEMINI_API_KEY")
    prompt = f"{CONSERVATIVE_SYSTEM}\n\nNews Information:\n{article}\n\nQuestion:\n{question}\n\nYour Report:"
    model_fallbacks = [model_name, "gemini-2.0-flash", "gemini-2.0-flash-lite"]

    try:
        if not key:
            # If no Gemini key at all, let Groq handle everything via fallback helper.
            print("⚠️  GEMINI_API_KEY missing. Using Groq-only fallback for this answer.")
        else:
            genai.configure(api_key=key)

        resp = generate_with_model_fallback(prompt, model_fallbacks)
        txt = (resp.text or "").strip()
        if not txt:
            raise RuntimeError("Empty response from Gemini/Groq")
        return txt

    except Exception as e:
        print(f"❌ Failed to generate answer for question '{question[:80]}...': {e}")
        # Bubble this up so the caller can cancel the whole run
        raise RuntimeError("Gemini/Groq generation failed") from e


# ========================= Main =========================

def main():
    ap = argparse.ArgumentParser(
        description="Auto-pick top story (optional) and generate sentence segments with Gemini/Groq."
    )
    ap.add_argument("--auto", action="store_true", help="Auto-select the most popular article now")
    ap.add_argument("--country", default="us", help="Country code for headlines")
    ap.add_argument("--topic", default="politics", help="Category/topic")
    ap.add_argument("--query", default="", help="Optional search keywords to bias selection")
    ap.add_argument("--story_url", default="", help="News article URL (ignored if --auto)")
    ap.add_argument("--story_title", default="", help="Optional title for Runs tab")
    ap.add_argument("--article_text", default="", help="Override: raw article text")
    ap.add_argument("--duration", type=float, default=4.0, help="Seconds each sentence is shown")
    ap.add_argument("--image-path-prefix", default="", help="Prefix to pre-fill image_path")
    ap.add_argument("--max-words", type=int, default=15, help="Max words per sentence")
    ap.add_argument("--min-words", type=int, default=10, help="Min words per sentence")
    ap.add_argument("--model", default="gemini-2.5-flash", help="Gemini model")

    args = ap.parse_args()
    sheet_key, _, _ = load_env_or_die()

    os.makedirs("generated", exist_ok=True)

    sh = open_sheet(sheet_key)
    titles = {ws.title for ws in sh.worksheets()}
    for tab in ("Questions", "Runs", "AnswerSegments"):
        if tab not in titles:
            sys.exit(f"Missing required tab: {tab}")
    questions = read_active_questions(sh)
    if not questions:
        sys.exit("No active questions in Questions tab (enabled != TRUE).")

    past_topics = get_past_topics(sh, num_past=3, model_name=args.model)
    recent_run_urls, recent_run_titlefps = get_recent_runs_dedupe(sh, num_past=12)

    url = args.story_url
    title = args.story_title
    article = args.article_text
    max_pick_attempts = 10
    published_at = None
    score = 0.0

    if args.auto:
        if news_picker is None:
            sys.exit("news_picker.py not found. Add it next to this script or disable --auto.")

        for attempt in range(max_pick_attempts):
            print(f"\n[auto] Attempting to pick top story (Attempt {attempt + 1}/{max_pick_attempts})...")
            picked = news_picker.pick_top_story(
                country=args.country,
                category=args.topic,
                query=(args.query or None),
            )

            if not picked:
                if attempt == 0:
                    sys.exit("Could not pick a top story on the first attempt. Check API key or adjust criteria.")
                print("⚠️ No new top stories found.")
                break

            url, title, published_at, score = picked

            # Secondary, sheet-based dedupe (handles ephemeral environments where .used.txt resets)
            try:
                c = news_picker.canonicalize_url(url)
                fp = news_picker.title_fingerprint(title)
                if c and c in recent_run_urls:
                    print("❌ URL matches a recent run (Runs sheet). Skipping.")
                    news_picker.mark_story_as_used(url, title)
                    time.sleep(1)
                    continue
                if fp and fp in recent_run_titlefps:
                    print("❌ Title is too similar to a recent run (Runs sheet). Skipping.")
                    news_picker.mark_story_as_used(url, title)
                    time.sleep(1)
                    continue
            except Exception as e:
                print(f"  ⚠️ Runs-sheet dedupe check failed (continuing): {e}")

            article = fetch_article_text(url)

            if article.startswith("(Fetch failed"):
                print(f"❌ Failed to fetch article text for {url}. Skipping.")
                news_picker.mark_story_as_used(url, title)
                time.sleep(1)
                continue

            if past_topics:
                current_topic = get_current_topic(article, args.model)
                if is_topic_duplicate(current_topic, past_topics, similarity_threshold=1):
                    print(f"❌ Story topic '{current_topic}' is too similar to past topics. Skipping.")
                    news_picker.mark_story_as_used(url, title)
                    time.sleep(1)
                    continue

            print(f"✅ Picked unique story: {title} ({url}) score={score:.3f}")
            save_article_data(url, title)
            news_picker.mark_story_as_used(url, title)
            break
        else:
            sys.exit(f"Could not find a unique article after {max_pick_attempts} attempts.")

    if not url:
        sys.exit("No story URL provided. Use --auto or pass --story_url.")

    if not article and not args.article_text:
        article = fetch_article_text(url)

    if article.startswith("(Fetch failed"):
        sys.exit(f"Could not retrieve article text for {url}.")

    run_id = now_run_id()
    rows_to_append = []
    last_successful_photo = ""
    gemini_request_count = 0

    try:
        for qid, qtext in questions:
            answer = gemini_answer(qtext, article, model_name=args.model)
            gemini_request_count += 1

            sents = limit_sentences_length(
                to_sentences(answer),
                max_words=args.max_words,
                min_words=args.min_words,
            )
            image_url = get_photo_url_for_answer(
                answer, article, qid, args.model, last_successful_photo
            )
            if image_url:
                last_successful_photo = image_url

            for idx, sent in enumerate(sents):
                img_path = (
                    image_url
                    if not args.image_path_prefix
                    else f"{args.image_path_prefix}{run_id}_{qid}_{idx}.png"
                )
                rows_to_append.append(
                    [run_id, qid, idx, sent, img_path, args.duration]
                )

            if gemini_request_count % 4 == 0 and gemini_request_count < len(questions):
                print("⏳ Pausing for 60 seconds to avoid Gemini rate limit...")
                time.sleep(60)

    except RuntimeError as e:
        # If any caption generation fails, cancel the entire run:
        # - no AnswerSegments
        # - no Runs row
        # - no run_id file
        print(f"❌ Segment generation failed for run {run_id}. Cancelling this run: {e}")
        return

    ws_segments = _with_retry(lambda: sh.worksheet("AnswerSegments"))
    append_rows_safe(ws_segments, rows_to_append)

    try:
        ws_runs = _with_retry(lambda: sh.worksheet("Runs"))
        _with_retry(
            lambda: ws_runs.append_rows(
                [[run_id, url, title or "", dt.datetime.utcnow().isoformat() + "Z", score]],
                value_input_option="RAW",
            )
        )
    except Exception:
        pass

    print(f"✅ Wrote {len(rows_to_append)} sentence segments for run {run_id}")

    try:
        with open("generated/run_id.txt", "w", encoding="utf-8") as f:
            f.write(run_id)
        print("✅ Saved run_id to generated/run_id.txt")
    except Exception as e:
        print(f"⚠️  Could not save run_id.txt: {e}")



if __name__ == "__main__":
    main()
