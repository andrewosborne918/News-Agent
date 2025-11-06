#!/usr/bin/env python3
"""
Quick test script to verify the fetch_article_text function works
with various URLs including Reuters.
"""

import sys
from generate_segments import fetch_article_text

def test_url(url: str):
    print(f"\n{'='*70}")
    print(f"Testing URL: {url}")
    print('='*70)
    
    try:
        text, success = fetch_article_text(url, timeout=20)
        
        print(f"\n{'✅' if success else '❌'} Fetch {'succeeded' if success else 'failed'}")
        print(f"Content length: {len(text)} characters")
        print(f"\nFirst 500 characters:")
        print("-" * 70)
        print(text[:500])
        print("-" * 70)
        
        return success
    except Exception as e:
        print(f"❌ Exception occurred: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Test user-provided URL
        test_url(sys.argv[1])
    else:
        # Test a few known URLs
        test_urls = [
            "https://www.bbc.com/news/world",
            "https://www.reuters.com/world/",
            "https://www.theguardian.com/world",
        ]
        
        print("Testing multiple URLs...")
        results = []
        for url in test_urls:
            success = test_url(url)
            results.append((url, success))
        
        print(f"\n{'='*70}")
        print("SUMMARY")
        print('='*70)
        for url, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status}: {url}")
