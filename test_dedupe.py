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
    assert c2 == "https://foxnews.com/politics/some-story"


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


def test_usedstories_url_hash_stable():
    """Sanity: the same story URL hashes the same after canonicalization."""
    import hashlib

    u1 = "http://www.foxnews.com/politics/some-story?utm_source=x&fbclid=abc"
    u2 = "https://foxnews.com/politics/some-story/"
    c1 = news_picker.canonicalize_url(u1)
    c2 = news_picker.canonicalize_url(u2)
    h1 = hashlib.sha1(c1.encode("utf-8")).hexdigest()
    h2 = hashlib.sha1(c2.encode("utf-8")).hexdigest()
    assert h1 == h2


if __name__ == "__main__":
    test_canonicalize_url_removes_tracking()
    test_title_fingerprint_matches_small_variations()
    test_is_duplicate_candidate_url_and_titlefp()
    test_usedstories_url_hash_stable()

    # Segmentation sanity checks (lightweight, no external deps)
    def _wrap_sentence_to_word_limit(sent: str, max_words: int):
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

    def _limit_sentences_length(sents, max_words: int, min_words: int = 10):
        out = []
        buffer = []
        for s in sents:
            words = s.split()
            wc = len(words)
            if wc > max_words:
                if buffer:
                    out.append(" ".join(buffer))
                    buffer = []
                out.extend(_wrap_sentence_to_word_limit(s, max_words))
            elif wc < min_words:
                buffer.append(s)
                buffered_words = sum(len(b.split()) for b in buffer)
                if buffered_words >= min_words:
                    combined = " ".join(buffer)
                    if len(combined.split()) <= max_words:
                        out.append(combined)
                    else:
                        out.extend(_wrap_sentence_to_word_limit(combined, max_words))
                    buffer = []
            else:
                if buffer:
                    combined = " ".join(buffer)
                    if len(combined.split()) <= max_words:
                        out.append(combined)
                    else:
                        out.extend(_wrap_sentence_to_word_limit(combined, max_words))
                    buffer = []
                out.append(s)
        if buffer:
            combined = " ".join(buffer)
            if len(combined.split()) <= max_words:
                out.append(combined)
            else:
                out.extend(_wrap_sentence_to_word_limit(combined, max_words))

        out = [x for x in out if x]
        i = 0
        while i < len(out):
            wc = len(out[i].split())
            if wc >= 3:
                i += 1
                continue
            if i > 0:
                candidate = (out[i - 1].rstrip() + " " + out[i].lstrip()).strip()
                if len(candidate.split()) <= max_words:
                    out[i - 1] = candidate
                    del out[i]
                    continue
            if i + 1 < len(out):
                candidate = (out[i].rstrip() + " " + out[i + 1].lstrip()).strip()
                if len(candidate.split()) <= max_words:
                    out[i + 1] = candidate
                    del out[i]
                    continue
            i += 1
        return out

    sents = [
        "Rep.",
        "Mike Lawler is calling for a vote.",
        "Today.",
        "Lawmakers are debating the bill in committee right now.",
    ]
    balanced = _limit_sentences_length(sents, max_words=15, min_words=10)
    # Goal: avoid ultra-short 1–2 word fragments.
    assert all(len(x.split()) > 2 for x in balanced), balanced

    print("✅ dedupe sanity checks passed")
