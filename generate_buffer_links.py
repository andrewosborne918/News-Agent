#!/usr/bin/env python3
"""
Generate Buffer sharing links for easy manual posting.
This bypasses the API completely - just click the links to add to Buffer queue.
"""

import os
import json
import urllib.parse
from pathlib import Path


def load_caption_data(caption_file="generated/caption.json"):
    """Load the AI-generated caption from file."""
    caption_path = Path(caption_file)
    
    if not caption_path.exists():
        print(f"⚠️  Caption file not found: {caption_file}")
        return None
    
    with open(caption_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_buffer_share_link(caption_data, video_filename="final.mp4"):
    """
    Generate a Buffer share link that pre-fills the post text.
    User just needs to click the link and upload the video manually.
    """
    
    if not caption_data:
        text = "📰 Today's political news analysis\n\n#News #Politics #Breaking"
    else:
        title = caption_data.get("title", "Political News Update")
        description = caption_data.get("description", "Watch for analysis")
        hashtags = caption_data.get("hashtags", ["News", "Politics"])
        
        # Format hashtags
        hashtag_string = " ".join([f"#{tag}" for tag in hashtags])
        
        # Create full caption
        text = f"{title}\n\n{description}\n\n{hashtag_string}"
    
    # URL encode the text
    encoded_text = urllib.parse.quote(text)
    
    # Buffer's share URL format
    buffer_url = f"https://buffer.com/add?text={encoded_text}"
    
    return buffer_url, text


def generate_markdown_instructions(caption_data, video_path, run_number):
    """Generate a markdown file with posting instructions."""
    
    buffer_link, caption_text = generate_buffer_share_link(caption_data)
    
    # Get video file size if it exists
    video_file = Path(video_path)
    video_size = f"{video_file.stat().st_size / 1024 / 1024:.2f} MB" if video_file.exists() else "N/A"
    
    markdown = f"""# Video #{run_number} - Ready to Post!

## 📹 Video Details
- **File**: `{video_path}`
- **Size**: {video_size}
- **Duration**: ~50 seconds
- **Format**: 1080x1920 (Portrait - Shorts/Reels ready)

---

## 📝 Caption (Copy & Paste)

```
{caption_text}
```

---

## 🚀 How to Post

### Option 1: Quick Buffer Link (Recommended)
1. **Click this link**: [{buffer_link}]({buffer_link})
2. It opens Buffer with caption pre-filled
3. Click **"Add to Queue"** or upload video
4. Select which accounts to post to
5. Done! ✅

### Option 2: Manual Post to Buffer
1. Go to: https://buffer.com
2. Click **"Create a Post"**
3. Paste the caption above
4. Upload video: `{video_path}`
5. Select: Facebook, YouTube, TikTok
6. Click **"Add to Queue"**

### Option 3: Direct Platform Posts
**Download video from GitHub Actions:**
- Go to: https://github.com/andrewosborne918/News-Agent/actions
- Click latest workflow run
- Download artifact: `news-video-{run_number}`

**Then post directly:**

#### Facebook Reels:
1. Open Facebook mobile app
2. Tap **Create** → **Reel**
3. Upload video
4. Paste caption
5. Post!

#### YouTube Shorts:
1. Open YouTube mobile app or Studio
2. Tap **+** → **Upload a Short**
3. Select video
4. Title: First line of caption
5. Description: Rest of caption
6. Post!

#### TikTok:
1. Open TikTok app
2. Tap **+** → **Upload**
3. Select video
4. Caption: {caption_text[:150]}...
5. Post!

---

## 📊 Caption Breakdown

**Title**: {caption_data.get('title', 'N/A') if caption_data else 'N/A'}

**Description**: {caption_data.get('description', 'N/A') if caption_data else 'N/A'}

**Hashtags**: {', '.join(['#' + tag for tag in caption_data.get('hashtags', [])]) if caption_data else 'N/A'}

---

## ⏰ Recommended Posting Times

Best engagement times (EST):
- **Morning**: 8-10am
- **Lunch**: 12-2pm  
- **Evening**: 6-9pm
- **Night**: 9-11pm

Current generation time: Check GitHub Actions timestamp

---

**Generated**: {run_number}
**Source**: News-Agent Automation
"""
    
    return markdown


def main():
    """Generate posting instructions and Buffer links."""
    
    # Get run number from environment or default
    run_number = os.getenv("RUN_NUMBER", "latest")
    video_path = "output/final.mp4"
    
    print("📝 Generating posting instructions...")
    
    # Load caption data
    caption_data = load_caption_data()
    
    if caption_data:
        print(f"✅ Loaded caption data")
        print(f"   Title: {caption_data['title']}")
    else:
        print("⚠️  Using default caption")
    
    # Generate Buffer share link
    buffer_link, caption_text = generate_buffer_share_link(caption_data)
    
    print("\n" + "="*60)
    print("🔗 BUFFER QUICK LINK")
    print("="*60)
    print(f"\n{buffer_link}\n")
    print("Just click this link to add to Buffer with caption pre-filled!")
    print("="*60)
    
    # Generate markdown instructions
    markdown = generate_markdown_instructions(caption_data, video_path, run_number)
    
    # Save to file
    output_file = f"output/POSTING_INSTRUCTIONS_{run_number}.md"
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown)
    
    print(f"\n✅ Saved posting instructions to: {output_file}")
    print("\n📋 CAPTION:")
    print("-" * 60)
    print(caption_text)
    print("-" * 60)
    
    print("\n🎯 NEXT STEPS:")
    print("1. Click the Buffer link above")
    print("2. Upload the video from output/final.mp4")
    print("3. Select platforms (Facebook, YouTube, TikTok)")
    print("4. Add to queue!")
    print("\nOr check the full instructions in:")
    print(f"   {output_file}")


if __name__ == "__main__":
    main()
