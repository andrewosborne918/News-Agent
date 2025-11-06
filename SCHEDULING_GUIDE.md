# Buffer Setup Complete Guide

You've connected Buffer to **Facebook, YouTube, and TikTok**. Here's how to complete the automation setup.

---

## ✅ Step 1: Get Your Buffer Access Token

1. Go to: https://account.buffer.com/developers/apps
2. Click **"Create App"** (or select existing app)
3. Fill in details:
   - **Name**: News Agent
   - **Description**: Automated news video posting
   - **Website**: https://github.com/andrewosborne918/News-Agent
4. Click **"Create App"**
5. **Copy your Access Token** (looks like: `1/abc123def456...`)

---

## ✅ Step 2: Test Locally (Optional but Recommended)

```bash
# Set your Buffer token temporarily
export BUFFER_ACCESS_TOKEN="your_token_here"

# Test the connection
python3 test_buffer_connection.py
```

You should see:
```
✅ Authentication successful!
👤 User: Your Name
📧 Email: your@email.com

✅ Found 3 connected account(s):

  1. FACEBOOK
     Username: @yourpage
     Profile ID: abc123
     Can schedule: Yes

  2. YOUTUBE
     Username: @yourchannel
     Profile ID: def456
     Can schedule: Yes

  3. TIKTOK
     Username: @youraccount
     Profile ID: ghi789
     Can schedule: Yes
```

---

## ✅ Step 3: Add Token to GitHub Secrets

1. Go to: https://github.com/andrewosborne918/News-Agent/settings/secrets/actions
2. Click **"New repository secret"**
3. Enter:
   - **Name**: `BUFFER_ACCESS_TOKEN`
   - **Value**: Paste your access token
4. Click **"Add secret"**

---

## ✅ Step 4: Configure Buffer Posting Schedule

### Option A: Queue to Your Schedule (Recommended)
Buffer will add videos to your queue and post according to your Buffer posting schedule.

1. Go to: https://buffer.com → **Settings** → **Posting Schedule**
2. Set your preferred times for each platform:
   - **Facebook**: e.g., 8am, 12pm, 4pm, 8pm
   - **YouTube**: e.g., 9am, 3pm, 9pm
   - **TikTok**: e.g., 10am, 2pm, 6pm, 10pm

Videos generated at 6am, 9am, 12pm, 3pm, 6pm will be added to your queue and posted at your next scheduled time.

### Option B: Post Immediately
To post videos immediately when generated:

1. Go to Buffer → **Settings** → **Posting Preferences**
2. Enable **"Post immediately"** or set to **"Top of Queue"**

---

## 📅 Automation Schedule

GitHub Actions will run at:
- **6:00 AM EST** (11:00 UTC)
- **9:00 AM EST** (14:00 UTC)
- **12:00 PM EST** (17:00 UTC)
- **3:00 PM EST** (20:00 UTC)
- **6:00 PM EST** (23:00 UTC)

Each run will:
1. ✅ Fetch trending political news
2. ✅ Generate AI commentary
3. ✅ Find relevant stock photos
4. ✅ Create video with background music
5. ✅ Generate engaging caption
6. ✅ Upload to Buffer queue
7. ✅ Buffer posts to Facebook, YouTube, TikTok

---

## 🎬 Video Format Per Platform

Buffer will automatically optimize for each platform:

### Facebook Reels
- ✅ Portrait 1080x1920 (already optimized)
- ✅ Up to 90 seconds (yours are ~50-70s)
- ✅ Music included
- ✅ Captions with hashtags

### YouTube Shorts
- ✅ Portrait 1080x1920 (already optimized)
- ✅ Up to 60 seconds (yours are ~50-70s)
- ⚠️ **Note**: Shorts should be under 60s
- ✅ Title and description from AI caption

### TikTok
- ✅ Portrait 1080x1920 (already optimized)
- ✅ Up to 10 minutes (yours are ~50-70s)
- ✅ Music included
- ✅ Hashtags optimized for TikTok

---

## ⚠️ Important Notes

### YouTube Shorts Duration
Your videos are 50-70 seconds, but **YouTube Shorts must be under 60 seconds**. 

**Option 1**: Reduce segment count (currently ~14 segments)
Edit `.github/workflows/news_agent.yml`:
```yaml
python generate_segments.py --auto --country us --topic politics --duration 3.5 --model "gemini-2.5-flash" --max-words 15 --min-words 10
```
Change `--duration 4.0` to `--duration 3.5` for ~50 second videos.

**Option 2**: Let Buffer handle it
Buffer may warn but will still post. YouTube might classify longer videos as regular videos instead of Shorts.

### Buffer Free vs Paid
- **Free**: 10 scheduled posts per profile
- **Paid**: Unlimited scheduled posts + analytics

If you hit the limit, upgrade at: https://buffer.com/pricing

---

## 🧪 Testing the Full Flow

### Manual Test Run

1. Go to: https://github.com/andrewosborne918/News-Agent/actions
2. Click **"News Agent (politics)"**
3. Click **"Run workflow"** → **"Run workflow"**
4. Watch the workflow execute (takes ~5-10 minutes)
5. Check Buffer queue: https://buffer.com

You should see:
- ✅ Video uploaded to Buffer
- ✅ Caption with title, description, hashtags
- ✅ Queued for Facebook, YouTube, TikTok

---

## 📊 Monitoring Your Posts

### Buffer Dashboard
- View queue: https://buffer.com
- See scheduled posts for each platform
- Analytics (paid plan)

### GitHub Actions
- View runs: https://github.com/andrewosborne918/News-Agent/actions
- Download generated videos (artifacts tab)
- Check logs for any errors

---

## 🔧 Troubleshooting

### "No accounts connected"
- **Fix**: Go to https://buffer.com and connect Facebook/YouTube/TikTok

### "Invalid access token"
- **Fix**: Regenerate token at https://account.buffer.com/developers/apps
- Update GitHub secret with new token

### "Video upload failed"
- **Cause**: Video too large (Buffer limit: 512 MB)
- **Fix**: Your videos are ~3 MB, so this shouldn't happen

### "Buffer queue full"
- **Cause**: Free plan limit (10 posts per profile)
- **Fix**: Upgrade to paid plan or manually clear old posts

### YouTube Shorts not showing as Shorts
- **Cause**: Video over 60 seconds
- **Fix**: Reduce `--duration` to 3.5 or less

---

## ✅ You're All Set!

Once you add `BUFFER_ACCESS_TOKEN` to GitHub Secrets, your system will:

1. **Automatically generate** 5 videos per day
2. **Post to all 3 platforms** (Facebook, YouTube, TikTok)
3. **Use AI captions** with engaging titles and hashtags
4. **Cycle background music** through your 4 tracks
5. **Run completely hands-free**

No more manual posting! 🎉

---

## 📞 Support

- Buffer API: https://buffer.com/developers/api
- Buffer Support: https://support.buffer.com
- GitHub Issues: https://github.com/andrewosborne918/News-Agent/issues
