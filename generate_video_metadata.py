#!/usr/bin/env python3
"""Create companion metadata JSON for the video upload.

Reads generated/caption.json to craft a tighter title and richer description.
Outputs: generated/news_video_<TIMESTAMP>.json (matching video filename).
Env:
  TIMESTAMP - required (should match mp4 name fragment)
"""
import os, json, re, sys, pathlib, string

ts = os.environ.get("TIMESTAMP")
if not ts:
  print("TIMESTAMP env var not set", file=sys.stderr)
  sys.exit(1)

caption_file = pathlib.Path("generated/caption.json")
caption = caption_file.read_text(encoding="utf-8") if caption_file.exists() else ""
raw = caption.strip()
text = re.sub(r"\s+", " ", raw)

# Extract first sentence or first N words
sentence_match = re.match(r"(.+?[.!?])\s", text + " ")
base_sentence = sentence_match.group(1) if sentence_match else text
words = base_sentence.split()

# Limit words
words = words[:16]
candidate = " ".join(words)

# Clean trailing punctuation
candidate = candidate.strip().rstrip(string.punctuation)

# Title casing with minor words preserved lowercase (unless first)
minor = {"a","an","and","or","but","for","nor","on","at","to","from","by","of","in","with","the"}
def smart_title(s: str) -> str:
  parts = s.split()
  out = []
  for i,p in enumerate(parts):
    lower = p.lower()
    if i != 0 and lower in minor:
      out.append(lower)
    else:
      out.append(p[:1].upper() + p[1:])
  return " ".join(out)

title = smart_title(candidate) or "Daily Politics Update"
title = title[:70]

description = (text or title)[:4800]
tags = ["news", "politics", "shorts", "breaking", "daily update"]

out = {"title": title, "description": description, "tags": tags}
out_path = pathlib.Path(f"generated/news_video_{ts}.json")
out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Written metadata JSON: {out_path}\nTitle: {title}\nDescription preview: {description[:120]}...")