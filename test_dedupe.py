#!/usr/bin/env python3
"""Basic sanity checks for news de-duplication helpers.

This is intentionally lightweight (no pytest dependency) so it can run anywhere.
"""

from __future__ import annotations

import news_picker


def test_canonicalize_url_removes_tracking():
    u1 = "https://www.foxnews.com/politics/some-story?utm_source=x&fbclid=abc"
    u2 = "http://foxnews.com/politics/some-story/"
    c1 = news_picker.canonicalize_url(u1)
    c2 = news_picker.canonicalize_url(u2)
    assert c1 == "https://foxnews.com/politics/some-story"
    assert c2 == "http://foxnews.com/politics/some-story"


def test_title_fingerprint_matches_small_variations():
    t1 = "Trump slams border bill - Fox News"
    t2 = "Trump slams border bill"
    fp1 = news_picker.title_fingerprint(t1)
    fp2 = news_picker.title_fingerprint(t2)
    assert fp1 == fp2


def test_is_duplicate_candidate_url_and_titlefp():
    d = news_picker.DedupState(
        used_urls={news_picker.canonicalize_url("https://foxnews.com/a?utm_source=x")},
        recent_keys={"titlefp:" + news_picker.title_fingerprint("hello world")},
    )
    assert news_picker.is_duplicate_candidate("https://foxnews.com/a", "new title", d)
    assert news_picker.is_duplicate_candidate("https://foxnews.com/b", "Hello, world!", d)
    assert not news_picker.is_duplicate_candidate("https://foxnews.com/c", "something else", d)


if __name__ == "__main__":
    test_canonicalize_url_removes_tracking()
    test_title_fingerprint_matches_small_variations()
    test_is_duplicate_candidate_url_and_titlefp()
    print("✅ dedupe sanity checks passed")
