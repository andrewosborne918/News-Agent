# Pexels Stock Photos Integration

## Overview

The News-Agent now uses **Pexels** to fetch free, high-quality stock photos instead of generating AI images. This provides:

- ✅ **Faster processing** - No waiting for AI image generation
- ✅ **Professional quality** - Real photography from professional photographers
- ✅ **Free to use** - All Pexels photos are royalty-free
- ✅ **Better relevance** - Photos are matched to question/answer content

## Setup

### 1. Get a Pexels API Key

1. Visit https://www.pexels.com/api/
2. Sign up for a free account
3. Copy your API key

### 2. Configure Your Environment

Add your Pexels API key to your `.env` file:

```bash
PEXELS_API_KEY=your_pexels_api_key_here
```

The `.env.example` file has been updated to include this variable.

### 3. Dependencies

The Pexels integration uses the `requests` library (already in `requirements.txt`), so no additional dependencies are needed.

## How It Works

### Keyword Extraction

The system automatically extracts relevant keywords from each question and answer:

1. Combines question text and answer text
2. Removes common stop words (the, is, are, etc.)
3. Keeps meaningful terms (4+ characters)
4. Uses top 3 keywords for search

Example:
- **Question**: "What is the main controversy in this story?"
- **Answer**: "The controversy centers around government spending and budget allocation."
- **Keywords**: `controversy government spending`

### Photo Selection

For each question, the system:

1. Searches Pexels with extracted keywords
2. Gets up to 30 results
3. Randomly selects one photo for variety
4. Uses portrait orientation (ideal for vertical videos)

### Fallback Strategy

If no photos are found:
1. Try again with just the question keywords
2. If still no results, use generic "abstract pattern" search
3. Ensures every segment has an image

## Usage

### Automatic (Default)

When you run `generate_segments.py`, it will automatically fetch Pexels photos:

```bash
python generate_segments.py --auto --country us --topic politics
```

### Testing

You can test the Pexels integration directly:

```bash
python pexels_photos.py
```

This will run a test search and display results.

## Code Structure

### `pexels_photos.py`

Main module with three key functions:

1. **`extract_keywords_from_text(text, max_keywords=3)`**
   - Extracts meaningful keywords from text
   - Returns a search query string

2. **`search_pexels_photo(query, per_page=30, orientation="portrait")`**
   - Searches Pexels API
   - Returns photo info dictionary or None

3. **`get_photo_for_question(question_text, answer_text="")`**
   - High-level function that combines extraction + search
   - Returns photo URL string
   - Used by `generate_segments.py`

### Integration in `generate_segments.py`

The old `generate_ai_horde_image_url()` function has been replaced with:

```python
def get_photo_url_for_question(question_text: str, answer_text: str, question_id: str) -> str:
    """
    Get a relevant stock photo from Pexels based on the question and answer.
    """
    if pexels_photos is None:
        print("⚠️ pexels_photos module not available")
        return ""
    
    try:
        print(f"  📸 Finding stock photo for {question_id}...")
        photo_url = pexels_photos.get_photo_for_question(question_text, answer_text)
        return photo_url
    except Exception as e:
        print(f"  ⚠️ Error fetching stock photo: {e}")
        return ""
```

## API Limits

### Free Tier (Pexels)

- **200 requests per hour**
- **20,000 requests per month**
- Rate limits are generous for typical use cases

### Typical Usage

If you generate segments 5 times per day with 5 questions each:
- **Daily**: 25 requests
- **Monthly**: ~750 requests

Well within free tier limits! 🎉

## Attribution

Pexels photos are royalty-free and don't require attribution, but it's good practice to credit photographers. The API response includes:

- `photographer` - Photographer name
- `photographer_url` - Link to photographer's profile
- `photo_url` - Link to photo on Pexels

You can add attribution in your video description if desired.

## Comparison: Pexels vs AI Horde

| Feature | Pexels | AI Horde (Old) |
|---------|--------|----------------|
| Speed | ⚡ Instant (~1-2s) | 🐌 Slow (30-120s per image) |
| Quality | ✅ Professional photos | ⚠️ Variable AI quality |
| Cost | 🆓 Free (20k/month) | 🆓 Free but slow queue |
| Relevance | ✅ Good keyword matching | ⚠️ Hit or miss |
| Reliability | ✅ Very reliable | ⚠️ Queue timeouts common |
| People in images | ✅ Can filter/control | ⚠️ Hard to avoid |

## Troubleshooting

### "PEXELS_API_KEY not found"

Make sure your `.env` file exists and contains:
```bash
PEXELS_API_KEY=your_actual_key_here
```

### "No photos found for query"

This is normal for very specific queries. The system will:
1. Try with broader keywords
2. Use fallback generic search
3. Always return some image

### Rate limit exceeded

If you hit the 200/hour limit:
- Wait an hour before generating more segments
- Consider caching frequently used photos
- Upgrade to Pexels Pro if needed (paid)

## Future Enhancements

Possible improvements:

- **Caching**: Store popular photos locally to reduce API calls
- **Photo variety**: Use different photos for each segment (not just per question)
- **Custom searches**: Allow manual keyword overrides per question
- **Attribution overlay**: Add photographer credits to video
- **Fallback sources**: Try Pixabay or Unsplash if Pexels fails

## Learn More

- Pexels API Docs: https://www.pexels.com/api/documentation/
- Pexels License: https://www.pexels.com/license/
