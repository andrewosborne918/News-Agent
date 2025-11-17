# news_picker.py
"""
NewsData.io integration for auto-picking top stories.

Usage:
    from news_picker import pick_top_story
    url, title, published_at, score = pick_top_story(country="us", category="politics")
"""

import os
import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser
from urllib.parse import urlparse

# YOUR LIST OF APPROVED SOURCES
TARGET_SOURCES = [
    "foxnews.com",
    "washingtontimes.com",
    "breitbart.com",
    "dailycaller.com"
]

def pick_top_story(country="us", category="politics", query=None):
    """
    Fetch the most popular or latest headline via NewsData.io.
    Returns (url, title, published_at_datetime_utc, score) or None.
    """
    api_key = os.getenv("NEWSDATA_API_KEY")
    if not api_key:
        raise RuntimeError("NEWSDATA_API_KEY missing in .env")

    # --- THIS IS THE FIX ---
    # We are changing this back to /api/1/news
    # This endpoint supports 'domain' and a non-empty 'q'
    base_url = "https://newsdata.io/api/1/news"
    # -----------------------

    # We tell the API to ONLY search these domains.
    domain_list = ",".join(TARGET_SOURCES)
    
    # We MUST provide a query ('q') when using 'domain'.
    # We will use the 'query' if provided, otherwise default to the 'category'.
    search_query = query or category

    params = {
        "apikey": api_key,
        "domain": domain_list,
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
    filtered_articles = []
    for a in articles:
        link = a.get("link") or ""
        if not link:
            continue
        
        try:
            # Get the domain (e.g., "www.foxnews.com" -> "foxnews.com")
            domain = urlparse(link).netloc
            if domain.startswith("www."):
                domain = domain[4:]
            
            if domain in TARGET_SOURCES:
                filtered_articles.append(a)
        except Exception:
            continue # Skip malformed URLs
    
    if not filtered_articles:
        print(f"⚠️ API returned articles, but none passed secondary domain validation for: {TARGET_SOURCES}")
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