#!/usr/bin/env python3
"""
make_video.py

Renders captions onto images and stitches them into a video with background music.
Uses Pillow for text overlay and ffmpeg for video generation.
"""

import os
import textwrap
import subprocess
import glob
import random
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# --------- Configuration ----------
INPUT_DIR   = Path("generated")
OUTPUT_DIR  = Path("output")
WORK_DIR    = Path("work")        # temp images with text baked in
MUSIC_DIR   = Path("assets")      # Directory containing background music MP3s
FONT_PATH   = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")  # System font
VIDEO_W, VIDEO_H = 1080, 1920     # Portrait mode (9:16 for TikTok/Reels/Shorts)
MIN_DURATION = 3                  # minimum seconds per slide
MAX_DURATION = 10                 # maximum seconds per slide
WORDS_PER_SECOND = 2.5            # legacy (kept for reference)
# Tuned reading speeds (slower for longer text)
WPS_SHORT = 2.2    # <= 15 words
WPS_MED   = 1.8    # 16-40 words
WPS_LONG  = 1.3    # > 40 words
FADE_SEC = 0.5                    # fade duration at transitions
FONT_SIZE = 70                    # readable size
MARGIN = 120                      # padding for text safe area (left/right & top/bottom)
LINE_WIDTH = 25                   # (unused for wrapping now; retained for backwards-compat)
# ----------------------------------

def ensure_dirs():
    """Create necessary directories"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    WORK_DIR.mkdir(exist_ok=True)
    print(f"✓ Directories ready: {OUTPUT_DIR}, {WORK_DIR}")

def calculate_duration(text):
    """Calculate slide duration based on text length with slower speeds for long text."""
    words = len(text.split())
    if words <= 15:
        wps = WPS_SHORT
    elif words <= 40:
        wps = WPS_MED
    else:
        wps = WPS_LONG
    duration = words / max(0.1, wps)
    # Slight extra buffer for very long captions
    if words > 60:
        duration *= 1.1
    # Clamp between min and max
    return max(MIN_DURATION, min(MAX_DURATION, duration))

def _text_width(draw, font, s: str):
    try:
        return draw.textlength(s, font=font)
    except Exception:
        bbox = draw.textbbox((0, 0), s, font=font)
        return bbox[2] - bbox[0]

def wrap_text_to_width(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int):
    """Wrap text by measuring pixel width so no line exceeds max_width.
    Splits overlong words as a last resort to avoid overflow.
    """
    words = text.split()
    lines = []
    cur = ""
    space = " "

    def flush():
        nonlocal cur
        if cur:
            lines.append(cur)
            cur = ""

    for w in words:
        trial = (cur + space + w).strip()
        if cur and _text_width(draw, font, trial) <= max_width:
            cur = trial
        elif not cur and _text_width(draw, font, w) <= max_width:
            cur = w
        else:
            # If current line has content, flush it first
            if cur:
                flush()
            # Handle very long single word by splitting
            if _text_width(draw, font, w) <= max_width:
                cur = w
            else:
                piece = ""
                for ch in w:
                    t2 = piece + ch
                    if _text_width(draw, font, t2) <= max_width:
                        piece = t2
                    else:
                        if piece:
                            lines.append(piece)
                        piece = ch
                if piece:
                    cur = piece
                else:
                    cur = ""
    flush()
    return lines

def load_font():
    """Load custom font or fallback to default"""
    try:
        if FONT_PATH.exists():
            print(f"✓ Using custom font: {FONT_PATH}")
            return ImageFont.truetype(str(FONT_PATH), FONT_SIZE)
        else:
            print("⚠ Custom font not found, using default")
            return ImageFont.load_default()
    except Exception as e:
        print(f"⚠ Font loading error: {e}, using default")
        return ImageFont.load_default()

def put_text_on_image(img_path, txt_path, out_path):
    """
    Overlay text on image with a translucent background bar.
    Handles portrait aspect ratio (9:16).
    """
    im = Image.open(img_path).convert("RGB")
    
    # Fill the entire frame by scaling to cover and cropping excess
    im_ratio = im.width / im.height
    vid_ratio = VIDEO_W / VIDEO_H
    
    if im_ratio > vid_ratio:
        # Image is wider - scale to height and crop sides
        scale = VIDEO_H / im.height
        new_w = int(im.width * scale)
        resized = im.resize((new_w, VIDEO_H), Image.LANCZOS)
        # Center crop
        x = (new_w - VIDEO_W) // 2
        canvas = resized.crop((x, 0, x + VIDEO_W, VIDEO_H))
    else:
        # Image is taller - scale to width and crop top/bottom
        scale = VIDEO_W / im.width
        new_h = int(im.height * scale)
        resized = im.resize((VIDEO_W, new_h), Image.LANCZOS)
        # Center crop
        y = (new_h - VIDEO_H) // 2
        canvas = resized.crop((0, y, VIDEO_W, y + VIDEO_H))

    # Draw semi-transparent overlay for text readability
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle([0, 0, VIDEO_W, VIDEO_H], fill=(0, 0, 0, 140))

    # Load and wrap text
    text = Path(txt_path).read_text(encoding="utf-8").strip() if Path(txt_path).exists() else ""
    font = load_font()
    # Pixel-aware wrapping within safe margins and centered vertically
    max_text_width = VIDEO_W - 2 * MARGIN
    lines = wrap_text_to_width(text, draw, font, max_text_width) if text else []

    # Compute total text block height
    line_heights = []
    max_w = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        max_w = max(max_w, w)
    spacing = 20
    text_h = sum(line_heights) + spacing * (max(0, len(lines) - 1))
    y = (VIDEO_H - text_h) // 2

    # Draw each line centered horizontally; margins ensure no clipping
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = max(MARGIN, (VIDEO_W - w) // 2)
        # Drop shadow
        draw.text((x+4, y+4), line, font=font, fill=(0, 0, 0, 255))
        # Main text
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_heights[i] + spacing

    canvas.save(out_path, quality=95)
    
    # Calculate duration based on text length
    duration = calculate_duration(text)
    print(f"  ✓ Rendered: {Path(img_path).name} -> {Path(out_path).name} ({duration:.1f}s)")
    
    return duration

def build_concat_list(image_files_with_durations):
    """Create ffmpeg concat demuxer input file with dynamic durations"""
    lst_path = WORK_DIR / "inputs.txt"
    with open(lst_path, "w", encoding="utf-8") as f:
        for img, duration in image_files_with_durations:
            # Use just the filename since files are in work/ directory
            filename = Path(img).name
            f.write(f"file '{filename}'\n")
            f.write(f"duration {duration}\n")
        # ffmpeg concat requires last file repeated without duration
        if image_files_with_durations:
            filename = Path(image_files_with_durations[-1][0]).name
            f.write(f"file '{filename}'\n")
    print(f"✓ Created concat list: {lst_path}")
    return lst_path

def run_ffmpeg(cmd, cwd=None):
    """Execute ffmpeg command"""
    print(f"🎬 Running ffmpeg...")
    print(f"   Command: {' '.join(cmd[:5])}...")
    if cwd:
        print(f"   Working dir: {cwd}")
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=cwd)
        print("   ✓ ffmpeg completed")
    except subprocess.CalledProcessError as e:
        # Capture stderr to see what went wrong
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        print(f"❌ ffmpeg failed with exit code {result.returncode}")
        print(f"Error output:\n{result.stderr}")
        raise

def main():
    print("="*60)
    print("🎥 News-Agent Video Generator")
    print("="*60)
    
    ensure_dirs()
    
    # Find all images and sort numerically by stem (e.g., 0001, 0002) regardless of extension
    patterns = ["*.jpg", "*.jpeg", "*.png"]
    images = []
    for pat in patterns:
        images.extend(glob.glob(str(INPUT_DIR / pat)))

    def numeric_key(p):
        try:
            return int(Path(p).stem)
        except ValueError:
            return float('inf')  # non-numeric names go last

    images = sorted(images, key=numeric_key)
    
    if not images:
        raise SystemExit(f"❌ No images found in {INPUT_DIR}")
    
    print(f"📸 Found {len(images)} images")

    # Render text on each image
    print("\n🖼️  Rendering captions on images...")
    baked_with_durations = []
    for img in images:
        stem = Path(img).stem
        txt = INPUT_DIR / f"{stem}.txt"
        out = WORK_DIR / f"{stem}_baked.jpg"
        duration = put_text_on_image(img, txt, out)
        baked_with_durations.append((str(out), duration))

    concat_file = build_concat_list(baked_with_durations)

    video_no_audio = OUTPUT_DIR / "slideshow.mp4"
    final_video = OUTPUT_DIR / "final.mp4"

    # Build slideshow with fade transitions
    total_duration = sum(d for _, d in baked_with_durations)
    print(f"\n🎬 Creating slideshow ({len(baked_with_durations)} slides, {total_duration:.1f}s total)...")
    
    # Use absolute paths for output, relative path for inputs (which are in work/)
    abs_video_no_audio = video_no_audio.absolute()
    
    run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", "inputs.txt",
        "-vf", "format=yuv420p",
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        str(abs_video_no_audio)
    ], cwd=WORK_DIR)

    # Mix in music if available
    music_files = sorted(MUSIC_DIR.glob("*.mp3"))  # Sort alphabetically for consistent ordering
    
    if music_files:
        # Use music files in order, cycling through them
        # Create a state file to track which track to use next
        state_file = MUSIC_DIR / ".music_index"
        
        # Read current index or start at 0
        if state_file.exists():
            try:
                current_index = int(state_file.read_text().strip())
            except (ValueError, FileNotFoundError):
                current_index = 0
        else:
            current_index = 0
        
        # Select the current track and advance to next
        selected_music = music_files[current_index % len(music_files)]
        next_index = (current_index + 1) % len(music_files)
        
        # Save the next index for next time
        state_file.write_text(str(next_index))
        
        print(f"\n🎵 Adding background music: {selected_music.name}")
        print(f"   (Track {current_index + 1} of {len(music_files)}, cycling through all tracks)")
        
        # Calculate fade durations (2 seconds fade in/out)
        fade_duration = 2.0
        
        # Add music with fade in/out, trimmed to video length
        run_ffmpeg([
            "ffmpeg", "-y",
            "-i", str(video_no_audio),
            "-i", str(selected_music),
            "-filter_complex",
            f"[1:a]afade=t=in:st=0:d={fade_duration},afade=t=out:st={total_duration - fade_duration}:d={fade_duration},volume=0.3[music];[music]atrim=0:{total_duration}[music_trimmed]",
            "-map", "0:v",
            "-map", "[music_trimmed]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(final_video)
        ])
        print(f"✅ Video with music: {final_video}")
        print(f"   ♪ Fade in/out: {fade_duration}s")
        print(f"   ♪ Volume: 30% (0.3)")
    else:
        print(f"⚠️  No MP3 files found in {MUSIC_DIR}, skipping audio")
        os.replace(video_no_audio, final_video)
        print(f"✅ Video (no audio): {final_video}")

    # Display file size
    size_mb = final_video.stat().st_size / (1024 * 1024)
    print(f"\n📊 Final video size: {size_mb:.2f} MB")
    print(f"⏱️  Duration: ~{total_duration}s")
    print("="*60)
    print("✅ Video generation complete!")
    print("="*60)

if __name__ == "__main__":
    main()
