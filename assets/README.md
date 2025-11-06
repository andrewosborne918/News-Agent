# Background Music

Place your MP3 files in this directory for use as background music in videos.

## How It Works

- The video generator will **randomly select** one MP3 file from this directory
- Music is automatically **trimmed** to match the video length
- **Fade in** (2 seconds at start) and **fade out** (2 seconds at end)  
- Volume is set to **30%** so it doesn't overpower the visuals

## Setup

Just drop your MP3 files here:

```
assets/
├── music1.mp3
├── music2.mp3
└── music3.mp3
```

The app will randomly pick one for each video!

## Supported Formats

- `.mp3` files only
- Any bitrate/quality
- Any length (will be auto-trimmed to video duration)

## Royalty-Free Music Sources

- **YouTube Audio Library**: https://www.youtube.com/audiolibrary
- **Free Music Archive**: https://freemusicarchive.org/
- **Incompetech**: https://incompetech.com/music/royalty-free/
- **Bensound**: https://www.bensound.com/

## No Music?

If no MP3 files are found, the video will be generated without audio (silent video).
