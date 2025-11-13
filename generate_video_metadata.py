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
article_file = pathlib.Path("generated/article.json")

# Get article title as a fallback
article_title = "Daily Politics Update"
if article_file.exists():
    try:
        article_data = json.loads(article_file.read_text(encoding="utf-8"))
        article_title = article_data.get("title", article_title)
    except (json.JSONDecodeError, KeyError):
        pass

# --- DEFAULTS ---
title = article_title
description = "Stay informed with our daily news shorts."
tags = ["news", "politics", "shorts", "breaking", "daily update"]
run_id = None # <-- ADDED

# Try to parse as JSON first (from generate_caption.py)
if caption_file.exists():
    try:
        caption_data = json.loads(caption_file.read_text(encoding="utf-8"))
        # Use the AI-generated title, description, and hashtags
        title = caption_data.get("title", article_title)[:70]
        description = caption_data.get("description", "")[:4800]
        # Convert hashtags to tags (remove # symbol)
        hashtags = caption_data.get("hashtags", [])
        tags = [tag.lstrip('#') for tag in hashtags] if hashtags else ["news", "politics", "shorts", "breaking"]
        run_id = caption_data.get("run_id") # <-- ADDED: Get the run_id
        
    except (json.JSONDecodeError, KeyError):
        # Fallback: treat as plain text
        caption = caption_file.read_text(encoding="utf-8")
        raw = caption.strip()
        text = re.sub(r"\s+", " ", raw)
        title = text[:70] or article_title
        description = text[:4800]
        tags = ["news", "politics", "shorts", "breaking", "daily update"]
else:
    # No caption file - use defaults
    pass # Defaults from above are used

# --- ADDED: Add run_id to the final JSON ---
out = {"title": title, "description": description, "tags": tags, "run_id": run_id}

out_path = pathlib.Path(f"generated/news_video_{ts}.json")
out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Written metadata JSON: {out_path}\nTitle: {title}\nDescription preview: {description[:120]}...\nRun ID: {run_id}")