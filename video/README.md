# News Agent Video Generator

Automatically generates vertical videos (1080x1920) from news segments using Remotion.

## Setup

### 1. Install Dependencies

```bash
# Python dependencies (if not already installed)
pip install -r requirements.txt

# Node.js dependencies
cd video && npm install
```

### 2. Generate News Segments

```bash
# Generate segments with stock photos from Pexels
python generate_segments.py --auto --country us --topic politics --duration 4.0 --model "gemini-2.5-flash" --max-words 15 --min-words 10
```

### 3. Render Video

```bash
# Render the latest run
python render_video.py

# Or render a specific run
python render_video.py run-20251105T214933Z
```

## How It Works

1. **`generate_segments.py`** - Fetches news, generates answers with Gemini, finds relevant stock photos
2. **`fetch_segments_for_video.py`** - Pulls segments from Google Sheets
3. **`render_video.py`** - Renders MP4 video using Remotion
4. **Video output** - Saved to `out/[run_id].mp4`

## Video Features

- **Vertical format**: 1080x1920 (TikTok/Reels/Shorts ready)
- **Animated text**: Fade-in with scale animation
- **Background images**: Professional stock photos from Pexels (royalty-free)
- **Dark overlay**: For text readability
- **Seamless transitions**: Each segment flows into the next

## Manual Preview

To preview in Remotion Studio:

```bash
cd video
npm start
```

Then open http://localhost:3000

## GitHub Actions

The workflow can be extended to automatically render videos:

1. Generate segments (already automated 5x daily)
2. Render video with Remotion
3. Upload to YouTube/TikTok

## File Structure

```
video/
├── src/
│   ├── Root.tsx          # Remotion composition entry
│   └── NewsVideo.tsx     # Main video component
├── public/
│   └── data.json         # Segments data (generated)
├── package.json
└── tsconfig.json

out/
└── [run_id].mp4          # Rendered videos
```

## Requirements

- **Node.js** 18+ (for Remotion)
- **Python** 3.10+
- **FFmpeg** (installed automatically by Remotion)
- **Chrome/Chromium** (for rendering)

## Troubleshooting

### "No segments found"
Run `generate_segments.py` first to create data in Google Sheets.

### "npm install fails"
Make sure you have Node.js 18+ installed: `node --version`

### Video rendering is slow
Rendering time depends on:
- Video length (4 seconds per segment)
- Image download speed
- Computer performance
- Typical: 1-2 minutes for a 60-second video

## Next Steps

- Add audio/voiceover with text-to-speech
- Customize fonts and colors
- Add transitions between segments
- Upload to social media platforms automatically
