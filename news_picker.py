"""news_picker.py

NewsData.io integration for auto-picking top stories.

This module also provides lightweight deduplication helpers.

Why stories were repeating before:
- URLs were compared as raw strings in `.used.txt`. Many publishers vary URLs with
  tracking params (utm_*, fbclid, etc.), https/http, or trailing slashes.
- Title/topic comparison only happened in `generate_segments.py` and depended on
  Gemini output (which can be unavailable or inconsistent).

Fix:
- Canonicalize URLs before comparing/storing.
- Maintain a simple local "recent keys" store of URL + title fingerprints.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional, Set

import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


# --------------------------------------------------------------------
# Dedup helpers
# --------------------------------------------------------------------

USED_URLS_FILE = os.getenv("NEWS_AGENT_USED_URLS_FILE", ".used.txt")
RECENT_KEYS_FILE = os.getenv("NEWS_AGENT_RECENT_KEYS_FILE", ".recent_story_keys.txt")


_DROP_QUERY_PREFIXES = (
    "utm_",
)
_DROP_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "refsrc",
    "cmpid",
    "guccounter",
}


def canonicalize_url(url: str) -> str:
    """Normalize a URL so the same story compares equal across tracking variants."""
    if not url:
        return ""
    try:
        u = urlparse(url.strip())
        scheme = (u.scheme or "https").lower()
        netloc = (u.netloc or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        # Normalize path (strip trailing slash except root)
        path = u.path or ""
        if path != "/":
            path = path.rstrip("/")

        # Filter tracking query params; stable sort for determinism
        q = []
        for k, v in parse_qsl(u.query or "", keep_blank_values=False):
            kl = k.lower()
            if any(kl.startswith(pfx) for pfx in _DROP_QUERY_PREFIXES):
                continue
            if kl in _DROP_QUERY_KEYS:
                continue
            q.append((kl, v))
        q.sort(key=lambda kv: kv[0])
        query = urlencode(q, doseq=True)

        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url.strip()


_TITLE_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those",
}


def normalize_title(title: str) -> str:
    """Normalize a title for comparison (punctuation/stopwords/case)."""
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"[\|\-\u2013\u2014]\s*[^\|\-\u2013\u2014]+$", "", t).strip()  # drop trailing " - Source"
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    words = [w for w in t.split() if w and w not in _TITLE_STOPWORDS]
    return " ".join(words)


def title_fingerprint(title: str, *, keep_words: int = 12) -> str:
    """Stable fingerprint so small edits to a headline still match."""
    norm = normalize_title(title)
    if not norm:
        return ""
    words = norm.split()[:keep_words]
    joined = " ".join(words)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def _read_lines(path: str) -> Set[str]:
    out: Set[str] = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s:
                    out.add(s)
    except FileNotFoundError:
        pass
    return out


def _append_line(path: str, value: str):
    if not value:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(value.strip() + "\n")
    except Exception as e:
        print(f"⚠️ Failed to write to {path}: {e}")


def get_used_urls() -> Set[str]:
    """Read used canonical URLs from local file."""
    return _read_lines(USED_URLS_FILE)


def mark_url_as_used(url: str):
    """Save canonical URL to the used-URLs list."""
    _append_line(USED_URLS_FILE, canonicalize_url(url))


def get_recent_story_keys() -> Set[str]:
    """Read recent story keys (canonical url + title fingerprint) from local file."""
    return _read_lines(RECENT_KEYS_FILE)


def mark_story_as_used(url: str, title: str = ""):
    """Persist both canonical URL and title fingerprint for robust dedupe."""
    c = canonicalize_url(url)
    if c:
        _append_line(USED_URLS_FILE, c)
        _append_line(RECENT_KEYS_FILE, f"url:{c}")
    fp = title_fingerprint(title)
    if fp:
        _append_line(RECENT_KEYS_FILE, f"titlefp:{fp}")
# YOUR LIST OF APPROVED SOURCES
TARGET_SOURCES = [
    "foxnews.com",
    "washingtontimes.com",
    "breitbart.com",
    "dailycaller.com"
]


@dataclass(frozen=True)
class DedupState:
    used_urls: Set[str]
    recent_keys: Set[str]


def default_dedup_state() -> DedupState:
    return DedupState(used_urls=get_used_urls(), recent_keys=get_recent_story_keys())


def is_duplicate_candidate(url: str, title: str, dedup: Optional[DedupState]) -> bool:
    """Return True if this story should be excluded based on local dedupe state."""
    if not dedup:
        return False
    c = canonicalize_url(url)
    if c and (c in dedup.used_urls or f"url:{c}" in dedup.recent_keys):
        return True
    fp = title_fingerprint(title)
    if fp and f"titlefp:{fp}" in dedup.recent_keys:
        return True
    return False


def pick_top_story(country="us", category="politics", query=None, *, dedup: Optional[DedupState] = None):
    """
    Fetch the most popular or latest headline via NewsData.io.
    Returns (url, title, published_at_datetime_utc, score) or None.
    """
    api_key = os.getenv("NEWSDATA_API_KEY")
    if not api_key:
        raise RuntimeError("NEWSDATA_API_KEY missing in .env")

    # We use the /api/1/news endpoint
    base_url = "https://newsdata.io/api/1/news"

    # We tell the API to ONLY search these domains.
    domain_list = ",".join(TARGET_SOURCES)
    
    # We MUST provide a query ('q') when using 'domainurl'.
    # We will use the 'query' if provided, otherwise default to the 'category'.
    search_query = query or category

    params = {
        "apikey": api_key,
        "domainurl": domain_list,  # <-- THIS IS THE FIX
        "language": "en",
        "q": search_query, # Use "politics" or the user's query
    }

    # remove None values
    params = {k: v for k, v in params.items() if v}

    try:
        r = requests.get(base_url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"❌ Failed to fetch from NewsData.io: {e}")
        return None

    if "results" not in data or not data["results"]:
        print(f"⚠️ No results from NewsData.io for domains {domain_list} with query '{search_query}'. Response: {data.get('status')}, message: {data.get('message', 'N/A')}")
        return None

    articles = data["results"]
    print(f"📰 Found {len(articles)} articles from NewsData.io (from target sources)")

    # --- Double-check filter (good practice) ---
    if dedup is None:
        dedup = default_dedup_state()

    filtered_articles = []
    for a in articles:
        link = a.get("link") or ""
        title = a.get("title") or ""
        if not link or is_duplicate_candidate(link, title, dedup):
            continue
        try:
            domain = urlparse(link).netloc
            if domain.startswith("www."):
                domain = domain[4:]
            if domain in TARGET_SOURCES:
                filtered_articles.append(a)
        except Exception:
            continue # Skip malformed URLs
    if not filtered_articles:
        print(f"⚠️ API returned articles, but none passed secondary domain validation for: {TARGET_SOURCES} or were already used.")
        return None
    # -------------------------------------------


    # High-interest political keywords (boost these stories)
    high_interest_keywords = [
        "trump", "biden", "harris", "mamdani", "obama", "clinton",
        "election", "vote", "ballot", "campaign",
        "congress", "senate", "house", "impeach",
        "white house", "presidential", "governor",
        "scandal", "investigation", "trial", "indictment",
        "supreme court", "justice", "ruling",
        "protest", "rally", "debate", "primary",
        "republican", "democrat", "gop",
        "policy", "bill", "legislation", "law",
        "war", "military", "ukraine", "china", "russia",
        "immigration", "border", "economy", "inflation"
    ]
    
    # Boring/skip keywords (penalize these)
    boring_keywords = [
        "stock", "shares", "trading", "analyst", "price target",
        "earnings", "revenue", "quarter", "financial",
        "reaffirms", "rating", "investment", "portfolio"
    ]

    best = None
    best_score = -1.0
    now = datetime.now(timezone.utc)
    
    for a in filtered_articles:
        title = a.get("title") or ""
        description = a.get("description") or ""
        link = a.get("link") or ""
        pub_date = a.get("pubDate") or a.get("published_date") or ""
        
        try:
            published = dateparser.parse(pub_date).astimezone(timezone.utc)
        except Exception:
            published = now

        # Recency scoring (prefer recent stories)
        minutes_old = max(1.0, (now - published).total_seconds() / 60)
        recency_score = 1.0 / (1.0 + (minutes_old / 180))  # half-life ~3h
        
        # Content score from API
        popularity_score = float(a.get("content_score") or 1.0)
        
        # Interest boost based on keywords
        title_lower = title.lower()
        desc_lower = description.lower()
        combined_text = f"{title_lower} {desc_lower}"
        
        interest_boost = 0.0
        for keyword in high_interest_keywords:
            if keyword in combined_text:
                interest_boost += 2.0  # Big boost for interesting topics
        
        # Penalty for boring financial stories
        boring_penalty = 0.0
        for keyword in boring_keywords:
            if keyword in combined_text:
                boring_penalty += 2.0  # Penalty for boring topics
        
        # Final score calculation
        score = recency_score + (popularity_score * 0.2) + interest_boost - boring_penalty
        
        if score > best_score:
            best = (link, title, published, score)
            best_score = score

    if best:
        print(f"✅ Picked top story: {best[1]} ({best[0]}) score={best[3]:.3f}")
        return best
    
    # Fallback: if no story scored positively, pick the least boring one
    print("⚠️ No story with positive score, picking least boring article as fallback")
    
    if filtered_articles:
        # Find article with fewest boring keywords
        least_boring = None
        min_boring_count = 999
        
        for fallback in filtered_articles:
            title = fallback.get("title") or ""
            description = fallback.get("description") or ""
            combined_text = f"{title.lower()} {description.lower()}"
            
            boring_count = sum(1 for kw in boring_keywords if kw in combined_text)
            
            if boring_count < min_boring_count:
                min_boring_count = boring_count
                least_boring = fallback
        
        if least_boring:
            link = least_boring.get("link") or ""
            title = least_boring.get("title") or "Untitled"
            pub_date = least_boring.get("pubDate") or least_boring.get("published_date") or ""
            try:
                published = dateparser.parse(pub_date).astimezone(timezone.utc)
            except Exception:
                published = now
            print(f"✅ Fallback story (boring_keywords={min_boring_count}): {title} ({link})")
            return (link, title, published, 0.0)
    
    print("⚠️ No articles available at all")
    return None