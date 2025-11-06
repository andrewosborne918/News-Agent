#!/usr/bin/env python3
"""
Fetch segments from Google Sheets and generate input data for Remotion video.
"""
import os
import sys
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from gspread.exceptions import APIError
import time
import random

def _with_retry(call, *, retries: int = 6, base_delay: float = 0.6, retriable_statuses=(429, 500, 502, 503, 504)):
    """Generic retry with exponential backoff for Sheets transient errors."""
    def _parse_status_code(err: Exception) -> int:
        try:
            code = getattr(err, "response", None)
            if code is not None:
                sc = getattr(code, "status_code", None)
                if sc:
                    return int(sc)
        except Exception:
            pass
        try:
            import re as _re
            m = _re.search(r"'code':\s*(\d+)", str(err))
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return 0

    for attempt in range(retries):
        try:
            return call()
        except APIError as e:
            code = _parse_status_code(e)
            if code in retriable_statuses and attempt < retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.25)
                print(f"  ⏳ Sheets API {code}; retrying in {delay:.2f}s (attempt {attempt+1}/{retries})")
                time.sleep(delay)
                continue
            raise
        except Exception as e:
            if attempt < retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.25)
                print(f"  ⏳ Transient error; retrying in {delay:.2f}s (attempt {attempt+1}/{retries}) - {e}")
                time.sleep(delay)
                continue
            raise

def fetch_latest_segments(sheet_key: str, creds_path: str, run_id: str = None):
    """Fetch segments from Google Sheets for the latest or specified run."""
    
    # Authenticate with Google Sheets
    creds = Credentials.from_service_account_file(
        creds_path,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(creds)
    sh = _with_retry(lambda: gc.open_by_key(sheet_key))
    
    # Get all segments
    ws = _with_retry(lambda: sh.worksheet('AnswerSegments'))
    rows = _with_retry(lambda: ws.get_all_records())
    
    if not rows:
        print("❌ No segments found in sheet")
        return None
    
    # Find the latest run_id if not specified
    if not run_id:
        run_id = max(r['run_id'] for r in rows if r.get('run_id'))
    
    print(f"📊 Fetching segments for run: {run_id}")
    
    # Filter segments for this run
    segments = []
    for r in rows:
        if r['run_id'] == run_id:
            segments.append({
                'sentence_text': r['sentence_text'],
                'image_path': r['image_path'],
                'duration_sec': float(r['duration_sec']) if r.get('duration_sec') else 4.0,
                'question_id': r['question_id'],
                'sentence_index': r.get('sentence_index', 0)
            })
    
    # Sort by a predefined section order, then by sentence_index to ensure proper order
    # Desired narrative order for the video
    section_order = [
        'what_happened',
        'why_it_matters',
        'conservative_angle',
        'next_steps',
    ]
    order_map = {name: i for i, name in enumerate(section_order)}

    def normalize_section(value: str) -> str:
        v = (value or '').strip().lower()
        if v.startswith('what'):
            return 'what_happened'
        if v.startswith('why'):
            return 'why_it_matters'
        if v.startswith('conservative'):
            return 'conservative_angle'
        if v.startswith('next'):
            return 'next_steps'
        return v

    # Normalize sentence_index to int to avoid lexicographic issues
    for s in segments:
        try:
            s['sentence_index'] = int(s.get('sentence_index') or 0)
        except Exception:
            s['sentence_index'] = 0

    for s in segments:
        s['question_id'] = normalize_section(s.get('question_id'))

    segments.sort(key=lambda x: (order_map.get(x['question_id'], 999), x['sentence_index']))
    
    print(f"✅ Found {len(segments)} segments")
    return {
        'run_id': run_id,
        'segments': segments
    }

def download_image(url: str, output_path: str):
    """Download an image from URL to local file"""
    import requests
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"⚠️  Failed to download {url}: {e}")
        return False

def save_segments_for_video(data: dict, output_dir: str = 'generated'):
    """Save segments as numbered image + text files for video generation"""
    import requests
    from pathlib import Path
    from PIL import Image, ImageDraw, ImageFont
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True, parents=True)
    
    print(f"\n📥 Downloading images and saving text to {output_dir}/")
    
    def make_placeholder(path: Path, message: str = "Image unavailable"):
        W, H = 1080, 1920
        img = Image.new("RGB", (W, H), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        except Exception:
            font = ImageFont.load_default()
        text_w, text_h = draw.textbbox((0,0), message, font=font)[2:]
        x = (W - text_w)//2
        y = (H - text_h)//2
        draw.text((x+2, y+2), message, font=font, fill=(0,0,0))
        draw.text((x, y), message, font=font, fill=(255,255,255))
        img.save(path, quality=90)

    for idx, seg in enumerate(data['segments'], start=1):
        # Save text file
        text_file = output_path / f"{idx:04d}.txt"
        text_file.write_text(seg['sentence_text'], encoding='utf-8')
        
        # Download and save image
        image_url = seg['image_path']
        if image_url and image_url.startswith('http'):
            # Determine extension from URL or default to jpg
            ext = '.jpg'
            if '.png' in image_url.lower():
                ext = '.png'
            elif '.jpeg' in image_url.lower() or '.jpg' in image_url.lower():
                ext = '.jpg'
            
            image_file = output_path / f"{idx:04d}{ext}"
            
            if download_image(image_url, str(image_file)):
                print(f"  ✓ {idx:04d}: {seg['sentence_text'][:50]}...")
            else:
                print(f"  ✗ {idx:04d}: Failed to download image — creating placeholder")
                image_file = output_path / f"{idx:04d}.jpg"
                make_placeholder(image_file)
        else:
            print(f"  ⚠️  {idx:04d}: No image URL — creating placeholder")
            image_file = output_path / f"{idx:04d}.jpg"
            make_placeholder(image_file)
    
    print(f"✅ Saved {len(data['segments'])} segments to {output_dir}/")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch segments from Google Sheets')
    parser.add_argument('--run-id', help='Specific run ID to fetch (defaults to latest)')
    parser.add_argument('--output-dir', default='generated', help='Output directory for images/text')
    parser.add_argument('--skip-video-files', action='store_true', help='Skip downloading images/text')
    args = parser.parse_args()
    
    load_dotenv()
    
    sheet_key = os.getenv('GOOGLE_SHEETS_KEY')
    creds_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON_PATH')
    
    if not sheet_key or not creds_path:
        sys.exit("❌ Missing GOOGLE_SHEETS_KEY or GOOGLE_SERVICE_ACCOUNT_JSON_PATH in .env")
    
    data = fetch_latest_segments(sheet_key, creds_path, args.run_id)
    
    if not data:
        sys.exit(1)
    
    # Write to JSON file for Remotion to consume
    output_path = 'video/public/data.json'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Written data to {output_path}")
    print(f"   Total duration: {sum(s['duration_sec'] for s in data['segments']):.1f} seconds")
    
    # Also save as images + text for video generation
    if not args.skip_video_files:
        save_segments_for_video(data, args.output_dir)

if __name__ == '__main__':
    main()
