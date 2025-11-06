# generate_segments.py - Quick Start Guide

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables** (`.env` file):
   ```bash
   GEMINI_API_KEY=your_gemini_api_key_here
   GOOGLE_SHEETS_KEY=your_google_sheet_key_here
   GOOGLE_SERVICE_ACCOUNT_JSON_PATH=credentials/service_account.json
   ```

3. **Verify Google Sheets setup:**
   - Sheet must have 3 tabs: `Questions`, `Runs`, `AnswerSegments`
   - Questions tab must have columns: `question_id`, `question_text`, `enabled`
   - Service account must have edit access to the sheet

---

## Basic Usage

### Standard run (automatic article fetch)
```bash
python generate_segments.py \
  --story_url "https://www.reuters.com/world/us/some-article-2024-11-05/" \
  --story_title "Breaking News Title" \
  --duration 4.0 \
  --max-words 26
```

### With image path prefix
```bash
python generate_segments.py \
  --story_url "https://example.com/article" \
  --story_title "Article Title" \
  --image-path-prefix "gs://my-bucket/segments/" \
  --duration 3.5 \
  --max-words 28
```

### Manual article text override (for difficult URLs)
```bash
# Copy article from file
python generate_segments.py \
  --story_url "https://paywalled-site.com/article" \
  --article_text "$(cat article.txt)" \
  --story_title "Article Title"

# Or paste directly
python generate_segments.py \
  --story_url "https://difficult-site.com/article" \
  --article_text "The article content goes here. This bypasses the automatic fetcher entirely." \
  --story_title "Article Title"
```

### Custom Gemini model
```bash
python generate_segments.py \
  --story_url "https://example.com/article" \
  --model "gemini-2.5-flash" \
  --max-words 30
```

---

## Command-Line Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--story_url` | ✅ Yes | - | News article URL to process |
| `--story_title` | No | `""` | Title for the Runs tab |
| `--duration` | No | `4.0` | Seconds each sentence is displayed |
| `--max-words` | No | `28` | Max words per sentence segment |
| `--image-path-prefix` | No | `""` | Prefix for image_path column (e.g., GCS bucket path) |
| `--model` | No | `gemini-2.5-flash` | Gemini model name |
| `--article_text` | No | `""` | Manual article text override (bypasses fetching) |

---

## Article Fetching Behavior

The script tries **three methods** in sequence until one succeeds:

1. **Normal GET** with browser-like headers
   - Most reliable for standard news sites
   
2. **Reuters AMP fallback** (automatic for reuters.com)
   - Tries `/amp` endpoint for Reuters URLs
   - AMP pages often have lighter anti-bot protection
   
3. **Reader proxy** (r.jina.ai)
   - Plain-text mirror as last resort
   - Cleans HTML and returns readable content

**Console output shows which method succeeded:**
```
📰 Fetching article from: https://www.reuters.com/world/...
  → Trying normal GET...
  → Normal GET failed: 401 Client Error
  → Trying Reuters AMP: https://www.reuters.com/world/.../amp
  ✓ Reuters AMP succeeded (8456 chars)
```

**If all methods fail:**
- Script continues with a generic error message
- Suggests using `--article_text` override
- Gemini generates neutral fallback text instead of crashing

---

## Output

### AnswerSegments Sheet
Appends rows with format:
```
[run_id, question_id, sentence_index, sentence_text, image_path, duration_sec]
```

Example:
```
run-20251105T143022Z | main_what | 0 | "The event occurred at 3pm local time." | gs://bucket/... | 4.0
run-20251105T143022Z | main_what | 1 | "Officials confirmed 15 people were affected." | gs://bucket/... | 4.0
run-20251105T143022Z | conservative_angle | 0 | "From a conservative viewpoint..." | gs://bucket/... | 4.0
```

### Runs Sheet
Appends one row per execution:
```
[run_id, story_url, story_title, published_at, popularity_score]
```

Example:
```
run-20251105T143022Z | https://example.com/article | "Breaking News" | 2025-11-05T14:30:22Z | 0.0
```

---

## Testing

### Test article fetching only
```bash
python test_fetch.py "https://www.reuters.com/world/some-article"
```

### Test with multiple URLs
```bash
python test_fetch.py
```

### Dry run (no API key needed)
Remove or comment out `GEMINI_API_KEY` in `.env`:
```bash
# Script will use mock answers instead of calling Gemini
python generate_segments.py --story_url "https://example.com/test"
```

---

## Troubleshooting

### "All fetch methods failed"
**Solution:** Use `--article_text` to provide content manually:
```bash
# Fetch with curl/wget first
curl -s "https://difficult-site.com/article" > raw.html
# Extract text manually or with a tool
python generate_segments.py \
  --story_url "https://difficult-site.com/article" \
  --article_text "$(cat extracted_text.txt)"
```

### "Gemini attempt 1 failed / attempt 2 failed"
**Possible causes:**
- Invalid API key → Check `.env`
- Quota exceeded → Wait or upgrade Gemini plan
- Network issues → Check internet connection

**Behavior:** Script uses neutral fallback text automatically

### "Warning: Content too short"
**When it appears:**
- Fetched content < 400 characters
- May indicate incomplete fetch or very brief article

**Actions:**
- Check the URL in a browser
- Try `--article_text` with fuller content
- If article is legitimately brief, ignore warning

### "Missing required tab(s)"
**Solution:** Ensure Google Sheet has these tabs:
- `Questions`
- `Runs`
- `AnswerSegments`

### "No active questions found"
**Solution:** In Questions tab, ensure:
- At least one row has `enabled = TRUE` (case-insensitive)
- Columns `question_id` and `question_text` exist

---

## Tips

1. **Reuters URLs:** Script automatically tries AMP fallback, usually works
2. **Long sentences:** Will be auto-split into chunks ≤ `--max-words`
3. **Image paths:** Fill `--image-path-prefix` if you have a media pipeline
4. **Model selection:** Stick with `gemini-2.5-flash` (default) to avoid 404 errors
5. **Batch processing:** Script handles multiple questions automatically
6. **Rate limits:** Add delays between runs if processing many articles

---

## Example Workflows

### Workflow 1: Standard Reuters article
```bash
python generate_segments.py \
  --story_url "https://www.reuters.com/world/us/trump-wins-election-2024-11-05/" \
  --story_title "Trump Wins Election" \
  --duration 4.0
```

### Workflow 2: Paywalled site with manual text
```bash
# Step 1: Get article text (via browser, archive.is, etc.)
cat > article.txt << 'EOF'
[Paste full article text here]
EOF

# Step 2: Run script with override
python generate_segments.py \
  --story_url "https://nytimes.com/paywalled-article" \
  --article_text "$(cat article.txt)" \
  --story_title "NYT Article Title"
```

### Workflow 3: Shorter segments for social media
```bash
python generate_segments.py \
  --story_url "https://example.com/article" \
  --max-words 20 \
  --duration 3.0
```

### Workflow 4: With image generation pipeline
```bash
python generate_segments.py \
  --story_url "https://example.com/article" \
  --image-path-prefix "gs://my-bucket/news-segments/" \
  --duration 4.0

# Later: use image_path column to generate/store images
```

---

## Next Steps

After running `generate_segments.py`:
1. Check AnswerSegments sheet for sentence segments
2. Generate images for each segment (separate pipeline)
3. Use segments for video/TikTok/social media content
4. Track performance via run_id in Runs sheet
