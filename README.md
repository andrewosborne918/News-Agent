# News-Agent

Automated political news video generator with AI-powered commentary, stock photos, background music, and social media posting.

## 🎯 What It Does

Fully automated system that runs 5x daily (6am-6pm EST):
1. **Fetches** trending political news from NewsData.io
2. **Generates** AI commentary using Google Gemini
3. **Creates** professional videos with Pexels stock photos and background music
4. **Produces** engaging captions with title, description, and hashtags
5. **Posts** automatically to social media via Buffer

## 🔄 Complete Automation Flow

```
Every 3 hours (6am, 9am, 12pm, 3pm, 6pm EST):
  ↓
1. NewsData.io API → Fetch trending political story
  ↓
2. Google Gemini AI → Generate news commentary segments
  ↓
3. Pexels API → Find relevant stock photos (portrait 512x768)
  ↓
4. FFmpeg → Build video with text overlays + background music
  ↓
5. Google Gemini AI → Analyze content & generate social caption
  ↓
6. Buffer API → Post with title, description, hashtags
  ↓
7. 🎉 Published to all connected social accounts!
```

## 📹 Video Generation

- **Format**: 1080x1920 portrait (optimized for TikTok/Instagram/Reels)
- **Images**: Pexels stock photos with AI-selected search terms
- **Text**: Dynamic overlays with DejaVu Sans Bold font
- **Duration**: 10-15 word chunks, dynamically timed (50-70 seconds total)
- **Music**: 4 background tracks cycling sequentially with fade in/out

## 🎵 Background Music

Videos cycle through 4 tracks in order:
1. "1 Unwavering Truth.mp3"
2. "2 Clear The Air.mp3"
3. "3 Facts On The Ground.mp3"
4. "4 We Could Get Along.mp3"

- Fade in/out: 2 seconds
- Volume: 30%
- Auto-trimmed to match video length

## 📝 AI Caption Generation

Each video gets a custom AI-generated caption:
- **Title**: Catchy headline (under 60 characters)
- **Description**: Compelling 2-3 sentences
- **Hashtags**: 5-8 relevant trending tags

Example:
```
Conservative Host Fears Midterm Disaster

A prominent conservative commentator voices serious concerns about upcoming elections. What this means for the GOP's future strategy.

#Politics #Elections #GOP #Midterms2024 #Conservative #Breaking #USPolitics
```

## 📅 Schedule

Videos generated and posted at:
- **6:00 AM EST** (11:00 UTC)
- **9:00 AM EST** (14:00 UTC)
- **12:00 PM EST** (17:00 UTC)
- **3:00 PM EST** (20:00 UTC)
- **6:00 PM EST** (23:00 UTC)

## 🔑 Required API Keys

Set up these secrets in GitHub Actions:
- `GEMINI_API_KEY` - Google Gemini AI
- `NEWSDATA_API_KEY` - NewsData.io
- `PEXELS_API_KEY` - Pexels stock photos
- `GOOGLE_SHEETS_KEY` - Google Sheets for data storage
- `GOOGLE_SERVICE_ACCOUNT_JSON_B64` - Base64-encoded service account JSON
- `BUFFER_ACCESS_TOKEN` - Buffer for social media posting

## 🚀 Quick Start

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Generate news content
python generate_segments.py --auto --country us --topic politics

# Generate video
python fetch_segments_for_video.py --output-dir generated
python video/make_video.py

# Generate caption
python generate_caption.py generated

# Post to Buffer
python post_to_buffer.py output/final.mp4
```

### GitHub Actions (Automated)

Already configured! Just add the required secrets and it runs automatically.

## 📁 Project Structure

```
news_agent_setup/
├── generate_segments.py      # Main content generator
├── news_picker.py            # NewsData.io integration
├── pexels_photos.py          # Stock photo fetcher
├── generate_caption.py       # AI caption generator
├── post_to_buffer.py         # Buffer API integration
├── video/
│   └── make_video.py        # FFmpeg video builder
├── fetch_segments_for_video.py
├── assets/                   # Background music MP3s
├── generated/                # Output directory
├── output/                   # Final video location
└── .github/workflows/
    └── news_agent.yml       # Automation workflow
```

## 🎨 Customization

### Change Schedule
Edit `.github/workflows/news_agent.yml`:
```yaml
schedule:
  - cron: "0 11,14,17,20,23 * * *"
```

### Modify Captions
Edit `generate_caption.py` prompt to adjust tone/style.

### Add More Music
Drop MP3 files in `assets/` - they'll cycle alphabetically.

### Change Video Format
Edit `video/make_video.py` to adjust resolution, font size, timing.

## 📊 Data Storage

- **Google Sheets**: Stores all generated segments and run history
- **Artifacts**: GitHub Actions saves videos for 30 days
- **Buffer Queue**: Posts managed through Buffer's scheduling system

## 🛠️ Troubleshooting

See `BUFFER_SETUP.md` for Buffer integration help.

Common issues:
- **No music in video**: MP3 files must be in `assets/` and committed to git
- **Caption generation fails**: Falls back to generic caption automatically
- **Buffer API errors**: Check token validity and connected accounts
- **Video generation fails**: Ensure FFmpeg and fonts are installed

## 📄 License

MIT

## 🙏 Credits

- Google Gemini for AI commentary
- NewsData.io for news articles
- Pexels for stock photography
- Buffer for social media management
