#!/usr/bin/env python3
"""
Complete workflow: Fetch segments and render video using Remotion.
"""
import os
import sys
import subprocess
from fetch_segments_for_video import fetch_latest_segments
from dotenv import load_dotenv
import json

def render_video(run_id: str = None):
    """Render video for the specified run_id (or latest)."""
    
    load_dotenv()
    
    sheet_key = os.getenv('GOOGLE_SHEETS_KEY')
    creds_path = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON_PATH')
    
    if not sheet_key or not creds_path:
        sys.exit("❌ Missing GOOGLE_SHEETS_KEY or GOOGLE_SERVICE_ACCOUNT_JSON_PATH")
    
    # Step 1: Fetch segments from Google Sheets
    print("\n📊 Step 1: Fetching segments from Google Sheets...")
    data = fetch_latest_segments(sheet_key, creds_path, run_id)
    
    if not data or not data['segments']:
        sys.exit("❌ No segments found")
    
    # Step 2: Write data file
    print("\n📝 Step 2: Writing data file...")
    os.makedirs('video/public', exist_ok=True)
    with open('video/public/data.json', 'w') as f:
        json.dump(data, f, indent=2)
    print(f"✅ Data written for {len(data['segments'])} segments")
    
    # Step 3: Install dependencies if needed
    if not os.path.exists('video/node_modules'):
        print("\n📦 Step 3: Installing Node.js dependencies...")
        subprocess.run(['npm', 'install'], cwd='video', check=True)
    else:
        print("\n✅ Step 3: Node.js dependencies already installed")
    
    # Step 4: Calculate total duration
    total_duration = sum(s['duration_sec'] for s in data['segments'])
    total_frames = int(total_duration * 30)  # 30 FPS
    
    print(f"\n🎬 Step 4: Rendering video...")
    print(f"   Run ID: {data['run_id']}")
    print(f"   Segments: {len(data['segments'])}")
    print(f"   Duration: {total_duration:.1f} seconds ({total_frames} frames)")
    
    # Step 5: Render with Remotion
    output_file = f"out/{data['run_id']}.mp4"
    os.makedirs('out', exist_ok=True)
    
    render_cmd = [
        'npx', 'remotion', 'render',
        'NewsVideo',
        output_file,
        '--props', f'{json.dumps(data)}',
        '--frames', str(total_frames)
    ]
    
    print(f"\n🎥 Rendering to {output_file}...")
    subprocess.run(render_cmd, cwd='video', check=True)
    
    print(f"\n✅ Video rendered successfully!")
    print(f"   Output: {output_file}")
    print(f"   Size: {os.path.getsize(output_file) / 1024 / 1024:.1f} MB")

if __name__ == '__main__':
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    render_video(run_id)
