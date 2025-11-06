"""
pexels_photos.py

Integration with Pexels API for fetching free stock photos.
Searches for relevant photos based on question content.
"""

import os
import requests
import random
import re
from typing import Optional, Dict


def extract_keywords_from_text(text: str, max_keywords: int = 3) -> str:
    """
    Extract relevant keywords from text for image search.
    Removes common stop words and focuses on meaningful terms.
    """
    # Common stop words to filter out
    stop_words = {
        "what", "how", "why", "when", "where", "who", "which", "whose",
        "is", "are", "was", "were", "be", "been", "being",
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "into", "through", "during",
        "about", "against", "between", "under", "over", "after", "before",
        "this", "that", "these", "those", "would", "could", "should",
        "might", "can", "may", "will", "shall", "must",
        "have", "has", "had", "do", "does", "did", "doing"
    }
    
    # Extract words (alphanumeric sequences)
    text_lower = text.lower()
    words = re.findall(r'\b[a-z]{4,}\b', text_lower)  # Only words with 4+ chars
    
    # Filter out stop words and duplicates
    keywords = []
    seen = set()
    for word in words:
        if word not in stop_words and word not in seen:
            keywords.append(word)
            seen.add(word)
            if len(keywords) >= max_keywords:
                break
    
    # Return joined keywords, or a default if none found
    return " ".join(keywords) if keywords else "news abstract"


def search_pexels_photo(query: str, per_page: int = 30, orientation: str = "portrait") -> Optional[Dict[str, str]]:
    """
    Search for stock photos on Pexels API.
    
    Args:
        query: Search query (keywords)
        per_page: Number of results to fetch (max 80)
        orientation: 'landscape', 'portrait', or 'square'
    
    Returns:
        Dictionary with photo info (url, photographer, etc.) or None if not found
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        print("⚠️ PEXELS_API_KEY not found in environment")
        return None
    
    url = "https://api.pexels.com/v1/search"
    
    headers = {
        "Authorization": api_key
    }
    
    params = {
        "query": query,
        "per_page": min(per_page, 80),  # Pexels max is 80
        "orientation": orientation
    }
    
    try:
        print(f"  📸 Searching Pexels for: '{query}'")
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        photos = data.get("photos", [])
        
        if not photos:
            print(f"  ⚠️ No photos found for query: '{query}'")
            return None
        
        # Select a random photo from results for variety
        photo = random.choice(photos)
        
        result = {
            "url": photo["src"]["large2x"],  # High quality image
            "alt_description": photo.get("alt", query),
            "photographer": photo["photographer"],
            "photographer_url": photo["photographer_url"],
            "photo_url": photo["url"]
        }
        
        print(f"  ✅ Found photo by {result['photographer']}")
        return result
        
    except requests.RequestException as e:
        print(f"  ⚠️ Pexels API error: {e}")
        return None


def get_photo_for_question(question_text: str, answer_text: str = "") -> str:
    """
    Get a Pexels photo URL relevant to the question and answer.
    
    Args:
        question_text: The question being asked
        answer_text: The answer text (optional, for more context)
    
    Returns:
        Photo URL string, or empty string if none found
    """
    # Combine question and answer for better keyword extraction
    combined_text = f"{question_text} {answer_text}"
    
    # Extract keywords
    keywords = extract_keywords_from_text(combined_text, max_keywords=3)
    
    # Search for photo
    photo = search_pexels_photo(keywords, per_page=30, orientation="portrait")
    
    if photo:
        return photo["url"]
    
    # Fallback: try with just the question
    if answer_text:
        keywords = extract_keywords_from_text(question_text, max_keywords=2)
        photo = search_pexels_photo(keywords, per_page=30, orientation="portrait")
        if photo:
            return photo["url"]
    
    # Final fallback: generic news/abstract image
    print("  ⚠️ Using fallback generic search")
    photo = search_pexels_photo("abstract pattern", per_page=20, orientation="portrait")
    return photo["url"] if photo else ""


if __name__ == "__main__":
    # Test the module
    from dotenv import load_dotenv
    load_dotenv()
    
    test_question = "What is the main controversy in this story?"
    test_answer = "The controversy centers around government spending and budget allocation."
    
    print("Testing Pexels photo search...")
    photo_url = get_photo_for_question(test_question, test_answer)
    
    if photo_url:
        print(f"\n✅ Success! Photo URL: {photo_url}")
    else:
        print("\n❌ Failed to get photo")
